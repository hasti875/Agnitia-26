"""
target.py
=========
Prediction target definition for real-world flood forecasting.

TARGET DEFINITION
-----------------
The target is a BINARY flood-event label:

    flood_event = 1  if river stage at (T + horizon) exceeds the
                     documented flood threshold for that gauge station
    flood_event = 0  otherwise

This is a scientifically defensible definition because:
  - It uses OBSERVED river stage (not rainfall alone)
  - It uses a DOCUMENTED threshold (not an arbitrary value)
  - It is aligned by location and timestamp
  - It does NOT use future information in the features

WHY NOT RAINFALL ALONE?
-----------------------
Rainfall is a necessary but NOT sufficient condition for flooding.
A region can receive heavy rain without flooding (good drainage,
low river base level). Conversely, a region can flood from upstream
rainfall even if local rainfall is moderate. Therefore:

  - Rainfall is used as a FEATURE (input to the model)
  - River stage exceedance is used as the TARGET (label)

WHY NOT THE SYNTHETIC flood_risk SCORE?
---------------------------------------
The synthetic flood_risk column in climate_history.csv is a formula
derived from synthetic inputs. It has no physical meaning in the
real world and must NOT be used as a ground-truth label.

CONFIGURABILITY
---------------
The prediction horizon is configurable (default 6 hours).
The flood threshold per gauge station is configurable via a
threshold mapping file.

LEAKAGE PREVENTION
------------------
1. Features at time T use only data from T and earlier.
2. The target at T is the flood label at T + horizon.
3. The split is chronological (train on earlier, test on later).
4. No future river stage or rainfall appears in any feature column.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import pandas as pd


# ---------------------------------------------------------------------------
# Default flood horizon (hours)
# ---------------------------------------------------------------------------
DEFAULT_HORIZON_HOURS = 6


# ---------------------------------------------------------------------------
# Flood threshold configuration
# ---------------------------------------------------------------------------

@dataclass
class FloodThresholdConfig:
    """
    Per-gauge-station flood threshold configuration.

    Each gauge station has a documented flood level (metres above
    local datum). When the observed river stage exceeds this level,
    a flood event is declared.

    If a gauge station is not in the mapping, the default threshold
    is used (or the station is excluded if no default is set).
    """
    thresholds: Dict[str, float] = field(default_factory=dict)
    default_threshold: Optional[float] = None
    source: str = "user-provided"
    notes: str = ""

    def get_threshold(self, gauge_id: str) -> Optional[float]:
        if gauge_id in self.thresholds:
            return self.thresholds[gauge_id]
        return self.default_threshold

    def to_dict(self) -> dict:
        return {
            "thresholds": dict(self.thresholds),
            "default_threshold": self.default_threshold,
            "source": self.source,
            "notes": self.notes,
        }


def load_threshold_config(
    config_path: Optional[str] = None,
) -> FloodThresholdConfig:
    """
    Load flood threshold configuration from a JSON file.

    Expected JSON format:
    {
        "thresholds": {
            "GAUGE_001": 4.5,
            "GAUGE_002": 3.8
        },
        "default_threshold": 4.0,
        "source": "CWC flood level documentation",
        "notes": "Thresholds from CWC 2023 flood level report"
    }

    If config_path is None or the file does not exist, returns an
    empty config (no thresholds defined).
    """
    if config_path is None:
        _here = os.path.dirname(os.path.abspath(__file__))
        config_path = os.path.join(
            os.path.dirname(_here), "data", "real", "flood_thresholds.json"
        )

    if not os.path.exists(config_path):
        return FloodThresholdConfig(
            notes=f"No threshold config found at {config_path}. "
                  "Flood labels cannot be derived without thresholds."
        )

    with open(config_path, "r", encoding="utf-8") as fh:
        raw = json.load(fh)

    return FloodThresholdConfig(
        thresholds={str(k): float(v) for k, v in raw.get("thresholds", {}).items()},
        default_threshold=raw.get("default_threshold"),
        source=raw.get("source", "unknown"),
        notes=raw.get("notes", ""),
    )


# ---------------------------------------------------------------------------
# Target derivation
# ---------------------------------------------------------------------------

def derive_flood_labels(
    river_data: pd.DataFrame,
    config: FloodThresholdConfig,
    horizon_hours: int = DEFAULT_HORIZON_HOURS,
) -> pd.DataFrame:
    """
    Derive binary flood-event labels from observed river stage data.

    Parameters
    ----------
    river_data : DataFrame with columns:
        - timestamp (pd.Timestamp, UTC)
        - area_id (str)
        - gauge_id (str, optional; falls back to area_id)
        - river_level_m (float, metres above local datum)
    config : FloodThresholdConfig with per-gauge thresholds.
    horizon_hours : Prediction horizon in hours (default 6).

    Returns
    -------
    DataFrame with the same index as river_data, plus columns:
        - flood_event (int 0/1): 1 if river_level_m > threshold
        - flood_threshold_m (float): the threshold used
        - future_flood_event (int 0/1): flood label at T + horizon
          (this is the ACTUAL target for the model)

    Notes
    -----
    - Rows where the gauge is not in the threshold config AND no
      default threshold is set get flood_event = NaN (excluded
      from training).
    - The future_flood_event is the target. It is the flood label
      at T + horizon, NOT at T. This is critical for leakage
      prevention: the model predicts whether a flood will occur
      6 hours from now, based on conditions at T.
    """
    out = river_data.copy()

    # Determine gauge_id (fall back to area_id if not present)
    if "gauge_id" not in out.columns:
        out["gauge_id"] = out["area_id"]

    # Assign threshold per row
    thresholds = out["gauge_id"].map(
        lambda g: config.get_threshold(str(g))
    )
    out["flood_threshold_m"] = thresholds

    # Derive current flood label (at T)
    valid = thresholds.notna()
    out["flood_event"] = 0
    out.loc[valid & (out["river_level_m"] > thresholds), "flood_event"] = 1
    out.loc[~valid, "flood_event"] = float("nan")

    # Derive FUTURE flood label (at T + horizon) — this is the target
    # We shift within each area/gauge group so that the target at row i
    # is the flood_event at row i + horizon (same location).
    #
    # IMPORTANT: This shift is applied to the flood_event column, which
    # is derived from river_level_m at T + horizon. The features at T
    # do NOT include river_level_m at T + horizon, so there is no
    # leakage.
    group_key = "gauge_id"
    out = out.sort_values([group_key, "timestamp"]).reset_index(drop=True)

    by_group = out.groupby(group_key, sort=False)
    out["future_flood_event"] = by_group["flood_event"].shift(-horizon_hours)

    # Drop rows where the future label is unknown (last `horizon_hours`
    # rows per gauge) or where the current label is undefined.
    # (The caller should dropna on future_flood_event before training.)

    return out


# ---------------------------------------------------------------------------
# Target summary report
# ---------------------------------------------------------------------------

def target_summary(
    labeled: pd.DataFrame,
    config: FloodThresholdConfig,
    horizon_hours: int = DEFAULT_HORIZON_HOURS,
) -> dict:
    """
    Produce a summary of the target variable for the data-quality report.

    Reports:
      - Total rows with valid labels
      - Number of positive labels (flood events)
      - Number of negative labels (no flood)
      - Class balance ratio
      - Number of rows excluded (no threshold defined)
      - Per-gauge event counts
    """
    valid = labeled["future_flood_event"].notna()
    valid_df = labeled[valid]

    n_total = len(labeled)
    n_valid = len(valid_df)
    n_excluded = n_total - n_valid

    n_positive = int((valid_df["future_flood_event"] == 1).sum())
    n_negative = int((valid_df["future_flood_event"] == 0).sum())

    class_balance = n_positive / n_negative if n_negative > 0 else float("inf")

    per_gauge = {}
    for gauge_id, group in valid_df.groupby("gauge_id"):
        per_gauge[str(gauge_id)] = {
            "n_rows": len(group),
            "n_flood_events": int((group["future_flood_event"] == 1).sum()),
            "n_no_flood": int((group["future_flood_event"] == 0).sum()),
            "threshold_m": config.get_threshold(str(gauge_id)),
        }

    return {
        "horizon_hours": horizon_hours,
        "n_total_rows": n_total,
        "n_valid_rows": n_valid,
        "n_excluded_rows": n_excluded,
        "n_positive_labels": n_positive,
        "n_negative_labels": n_negative,
        "class_balance_pos_neg": round(class_balance, 4),
        "per_gauge": per_gauge,
        "threshold_config": config.to_dict(),
    }
