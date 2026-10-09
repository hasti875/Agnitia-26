"""
risk_engine.py
==============
Explainable Current Climate Risk Engine
Phase 3 — Climate Risk Arbitrage Engine (hackathon MVP)

PURPOSE
-------
Calculate a transparent, rule-based flood-risk score (0–100) for each region
using the *current* (latest available) climate observations.

This is NOT machine-learning forecasting.
Phase 4 will separately train a RandomForestRegressor to FORECAST future risk.
This module produces a baseline "right now" risk that is always explainable
from first principles, even when the ML model is unavailable.

RISK DECOMPOSITION
------------------
                        ┌─────────────────────────────────┐
                        │         FLOOD RISK  (0–100)     │
                        └──────────┬─────────────┬────────┘
                                   │             │
                        ┌──────────▼──┐     ┌────▼──────────────┐
                        │  HAZARD     │     │  VULNERABILITY ×  │
                        │  (0–1)      │     │  EXPOSURE   (0–1) │
                        └─────────────┘     └───────────────────┘

  HAZARD sub-components (weights sum to 1.0):
    recent_rainfall_score    0.35  — last observed hour, normalised
    cumulative_rain_score    0.30  — rolling 6-hr total, normalised
    river_level_score        0.20  — exceedance above danger level
    river_trend_score        0.15  — rising vs falling river

  VULNERABILITY sub-components (weights sum to 1.0):
    vulnerability_index      0.50  — composite socio-physical fragility
    road_inaccessibility     0.30  — 1 − road_accessibility (harder exit = worse)
    historical_flood_freq    0.20  — how often this area has flooded

  EXPOSURE sub-components (weights sum to 1.0):
    population_density_norm  0.60  — people per km², normalised
    population_norm          0.40  — absolute population, normalised

  FINAL COMBINATION:
    risk_score = hazard × (BASE_WEIGHT + VUL_EXP_WEIGHT × vul_exp_score) × 100

  Where:
    BASE_WEIGHT     = 0.60  (hazard always contributes even with zero vulnerability)
    VUL_EXP_WEIGHT  = 0.40  (vulnerability/exposure amplifies or dampens hazard)

  This mirrors the established HEV (Hazard × Exposure × Vulnerability) framework
  used in disaster risk indices such as the UNDRR Global Assessment Report.

RISK CATEGORIES
---------------
  0–30   LOW
  31–50  MODERATE
  51–70  HIGH
  71–85  VERY HIGH
  86–100 CRITICAL
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DATA_DIR    = os.path.join(_BACKEND_DIR, "data")
CLIMATE_CSV  = os.path.join(_DATA_DIR, "climate_history.csv")

# ---------------------------------------------------------------------------
# Configurable weights — change here rather than digging into formulas
# ---------------------------------------------------------------------------

HAZARD_WEIGHTS: Dict[str, float] = {
    "recent_rainfall":   0.35,
    "cumulative_rain":   0.30,
    "river_level":       0.20,
    "river_trend":       0.15,
}

VULNERABILITY_WEIGHTS: Dict[str, float] = {
    "vulnerability_index":    0.50,
    "road_inaccessibility":   0.30,
    "historical_flood_freq":  0.20,
}

EXPOSURE_WEIGHTS: Dict[str, float] = {
    "population_density": 0.60,
    "population":         0.40,
}

# Final combination constants
BASE_WEIGHT    = 0.60   # hazard floor even when vulnerability = 0
VUL_EXP_WEIGHT = 0.40   # maximum amplification from vulnerability + exposure

# Normalisation ceilings — values at or above these saturate the component at 1.0
RAIN_RECENT_MAX_MM   = 30.0    # mm/hr that = max recent rainfall hazard
RAIN_CUMUL_MAX_MM    = 80.0    # mm in 6 hrs that = max cumulative hazard
RIVER_EXCEED_RANGE_M = 3.0     # metres above danger threshold = max river hazard
RIVER_TREND_MAX_M    = 1.5     # metres/3hr rise that = max trend hazard
POP_DENSITY_MAX      = 3000.0  # per km² — normalisation ceiling
POP_MAX_THOUSANDS    = 3500.0  # population in thousands — normalisation ceiling

# River danger thresholds (metres) per region — below this = no hazard
REGION_DANGER_LEVELS: Dict[str, float] = {
    "IND": 3.30,   # base 1.8 + 1.5
    "UJJ": 3.70,
    "DEW": 3.50,
    "DHA": 4.00,
    "RAT": 3.40,
    "MAN": 3.20,
    "MHO": 4.30,
    "SEH": 3.80,
}
DEFAULT_DANGER_LEVEL = 3.50    # fallback if area_id not found

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class AreaObservation:
    """A snapshot of climate + static variables for one region at one moment."""
    area_id:                   str
    area_name:                 str
    timestamp:                 pd.Timestamp
    rainfall_mm:               float        # last-hour rainfall
    cumulative_rain_6h:        float        # sum of last 6 hours (inclusive)
    river_level_m:             float
    river_trend_3h:            float        # level now minus level 3 hrs ago
    temperature_c:             float
    humidity:                  float
    historical_flood_frequency: float       # 0–1
    population:                float        # thousands
    population_density:        float        # per km²
    vulnerability_index:       float        # 0–1
    road_accessibility:        float        # 0–1


@dataclass
class RiskResult:
    """Full risk assessment for one region."""
    area_id:             str
    area_name:           str
    timestamp:           pd.Timestamp
    risk_score:          float            # 0–100
    risk_level:          str             # LOW / MODERATE / HIGH / VERY HIGH / CRITICAL
    hazard_score:        float            # 0–1
    exposure_score:      float            # 0–1
    vulnerability_score: float            # 0–1
    # Sub-component scores for transparency
    recent_rainfall_score:  float
    cumulative_rain_score:  float
    river_level_score:      float
    river_trend_score:      float
    key_factors:            str
    # Raw inputs echoed for convenience
    rainfall_mm:            float
    cumulative_rain_6h:     float
    river_level_m:          float
    river_trend_3h:         float

    def to_dict(self) -> dict:
        return {
            "area_id":            self.area_id,
            "area_name":          self.area_name,
            "timestamp":          str(self.timestamp),
            "risk_score":         round(self.risk_score, 2),
            "risk_level":         self.risk_level,
            "hazard_score":       round(self.hazard_score, 4),
            "exposure_score":     round(self.exposure_score, 4),
            "vulnerability_score": round(self.vulnerability_score, 4),
            "recent_rainfall_score": round(self.recent_rainfall_score, 4),
            "cumulative_rain_score": round(self.cumulative_rain_score, 4),
            "river_level_score":  round(self.river_level_score, 4),
            "river_trend_score":  round(self.river_trend_score, 4),
            "rainfall_mm":        round(self.rainfall_mm, 2),
            "cumulative_rain_6h": round(self.cumulative_rain_6h, 2),
            "river_level_m":      round(self.river_level_m, 3),
            "river_trend_3h":     round(self.river_trend_3h, 3),
            "key_factors":        self.key_factors,
        }


# ---------------------------------------------------------------------------
# Core scoring functions
# ---------------------------------------------------------------------------

def calculate_hazard_score(
    rainfall_mm:        float,
    cumulative_rain_6h: float,
    river_level_m:      float,
    river_trend_3h:     float,
    area_id:            str = "UNKNOWN",
    weights:            Optional[Dict[str, float]] = None,
) -> tuple[float, float, float, float, float]:
    """
    Calculate the HAZARD score (0–1) from physical climate variables.

    Parameters
    ----------
    rainfall_mm         : Rainfall in the most recent hour (mm).
    cumulative_rain_6h  : Total rainfall over the last 6 hours (mm).
    river_level_m       : Current river level (metres).
    river_trend_3h      : Change in river level over the last 3 hours (metres).
                          Positive = rising.  Negative = falling.
    area_id             : Region identifier used to look up the danger threshold.
    weights             : Override default HAZARD_WEIGHTS if provided.

    Returns
    -------
    hazard_score, recent_rain_sub, cumul_rain_sub, river_level_sub, river_trend_sub
    All values 0–1.
    """
    w = weights or HAZARD_WEIGHTS
    assert abs(sum(w.values()) - 1.0) < 1e-9, "HAZARD_WEIGHTS must sum to 1.0"

    # Sub-component 1 — recent rainfall
    recent_rain_sub = float(np.clip(rainfall_mm / RAIN_RECENT_MAX_MM, 0.0, 1.0))

    # Sub-component 2 — cumulative 6-hour rainfall
    cumul_rain_sub = float(np.clip(cumulative_rain_6h / RAIN_CUMUL_MAX_MM, 0.0, 1.0))

    # Sub-component 3 — river level exceedance above danger threshold
    danger_level = REGION_DANGER_LEVELS.get(area_id, DEFAULT_DANGER_LEVEL)
    exceedance   = max(0.0, river_level_m - danger_level)
    river_level_sub = float(np.clip(exceedance / RIVER_EXCEED_RANGE_M, 0.0, 1.0))

    # Sub-component 4 — river trend (rising = high hazard, falling = low)
    # Normalise: +RIVER_TREND_MAX_M rise → 1.0; -RIVER_TREND_MAX_M fall → 0.0
    river_trend_sub = float(
        np.clip((river_trend_3h + RIVER_TREND_MAX_M) / (2 * RIVER_TREND_MAX_M), 0.0, 1.0)
    )

    hazard_score = (
        w["recent_rainfall"] * recent_rain_sub
        + w["cumulative_rain"] * cumul_rain_sub
        + w["river_level"]    * river_level_sub
        + w["river_trend"]    * river_trend_sub
    )

    return (
        float(np.clip(hazard_score, 0.0, 1.0)),
        recent_rain_sub,
        cumul_rain_sub,
        river_level_sub,
        river_trend_sub,
    )


def calculate_vulnerability_score(
    vulnerability_index:       float,
    road_accessibility:        float,
    historical_flood_frequency: float,
    weights: Optional[Dict[str, float]] = None,
) -> float:
    """
    Calculate the VULNERABILITY score (0–1).

    Parameters
    ----------
    vulnerability_index        : Composite socio-physical fragility (0–1).
    road_accessibility         : Road quality / reach (0–1, higher = better).
    historical_flood_frequency : Fraction of past seasons with flood events (0–1).
    weights                    : Override default VULNERABILITY_WEIGHTS if provided.

    Returns
    -------
    vulnerability_score in [0, 1].
    """
    w = weights or VULNERABILITY_WEIGHTS
    assert abs(sum(w.values()) - 1.0) < 1e-9, "VULNERABILITY_WEIGHTS must sum to 1.0"

    road_inaccessibility = 1.0 - float(np.clip(road_accessibility, 0.0, 1.0))

    score = (
        w["vulnerability_index"]   * float(np.clip(vulnerability_index, 0.0, 1.0))
        + w["road_inaccessibility"]  * road_inaccessibility
        + w["historical_flood_freq"] * float(np.clip(historical_flood_frequency, 0.0, 1.0))
    )

    return float(np.clip(score, 0.0, 1.0))


def calculate_exposure_score(
    population:        float,
    population_density: float,
    weights: Optional[Dict[str, float]] = None,
) -> float:
    """
    Calculate the EXPOSURE score (0–1).

    Parameters
    ----------
    population         : Population in thousands.
    population_density : People per km².
    weights            : Override default EXPOSURE_WEIGHTS if provided.

    Returns
    -------
    exposure_score in [0, 1].
    """
    w = weights or EXPOSURE_WEIGHTS
    assert abs(sum(w.values()) - 1.0) < 1e-9, "EXPOSURE_WEIGHTS must sum to 1.0"

    pop_density_norm = float(np.clip(population_density / POP_DENSITY_MAX, 0.0, 1.0))
    pop_norm         = float(np.clip(population / POP_MAX_THOUSANDS, 0.0, 1.0))

    score = (
        w["population_density"] * pop_density_norm
        + w["population"]         * pop_norm
    )

    return float(np.clip(score, 0.0, 1.0))


def calculate_flood_risk(obs: AreaObservation) -> RiskResult:
    """
    Combine HAZARD, VULNERABILITY and EXPOSURE into a single flood-risk score
    and produce an explainable RiskResult.

    Formula
    -------
        vul_exp  = 0.5 × vulnerability_score + 0.5 × exposure_score
        multiplier = BASE_WEIGHT + VUL_EXP_WEIGHT × vul_exp
        risk_score = hazard_score × multiplier × 100

    The multiplier ranges from BASE_WEIGHT (0.60) when both vulnerability and
    exposure are zero, to BASE_WEIGHT + VUL_EXP_WEIGHT (1.00) at maximum
    vulnerability/exposure.  This ensures hazard always drives the score but
    vulnerability and exposure meaningfully amplify it.
    """
    hazard, rr_sub, cr_sub, rl_sub, rt_sub = calculate_hazard_score(
        rainfall_mm        = obs.rainfall_mm,
        cumulative_rain_6h = obs.cumulative_rain_6h,
        river_level_m      = obs.river_level_m,
        river_trend_3h     = obs.river_trend_3h,
        area_id            = obs.area_id,
    )

    vulnerability = calculate_vulnerability_score(
        vulnerability_index        = obs.vulnerability_index,
        road_accessibility         = obs.road_accessibility,
        historical_flood_frequency = obs.historical_flood_frequency,
    )

    exposure = calculate_exposure_score(
        population         = obs.population,
        population_density = obs.population_density,
    )

    # Combine vulnerability and exposure equally
    vul_exp    = 0.5 * vulnerability + 0.5 * exposure
    multiplier = BASE_WEIGHT + VUL_EXP_WEIGHT * vul_exp
    risk_score = float(np.clip(hazard * multiplier * 100, 0.0, 100.0))

    risk_level = classify_risk(risk_score)
    key_factors = _build_key_factors(
        rr_sub, cr_sub, rl_sub, rt_sub,
        vulnerability, exposure,
        obs.rainfall_mm, obs.cumulative_rain_6h,
        obs.river_level_m, obs.river_trend_3h,
        obs.area_id,
    )

    return RiskResult(
        area_id              = obs.area_id,
        area_name            = obs.area_name,
        timestamp            = obs.timestamp,
        risk_score           = risk_score,
        risk_level           = risk_level,
        hazard_score         = hazard,
        exposure_score       = exposure,
        vulnerability_score  = vulnerability,
        recent_rainfall_score = rr_sub,
        cumulative_rain_score = cr_sub,
        river_level_score    = rl_sub,
        river_trend_score    = rt_sub,
        key_factors          = key_factors,
        rainfall_mm          = obs.rainfall_mm,
        cumulative_rain_6h   = obs.cumulative_rain_6h,
        river_level_m        = obs.river_level_m,
        river_trend_3h       = obs.river_trend_3h,
    )


def classify_risk(score: float) -> str:
    """
    Map a numeric risk score (0–100) to a human-readable risk level.

    Bands
    -----
      0–30   → LOW
      31–50  → MODERATE
      51–70  → HIGH
      71–85  → VERY HIGH
      86–100 → CRITICAL
    """
    if score <= 30:
        return "LOW"
    elif score <= 50:
        return "MODERATE"
    elif score <= 70:
        return "HIGH"
    elif score <= 85:
        return "VERY HIGH"
    else:
        return "CRITICAL"


# ---------------------------------------------------------------------------
# Explanation builder
# ---------------------------------------------------------------------------

def _build_key_factors(
    rr_sub: float, cr_sub: float, rl_sub: float, rt_sub: float,
    vulnerability: float, exposure: float,
    rainfall_mm: float, cumul_rain: float,
    river_level: float, river_trend: float,
    area_id: str,
) -> str:
    """
    Build a plain-English sentence describing the dominant risk drivers.
    Uses only actual calculated scores — no LLM or template API.
    """
    factors: List[str] = []

    # --- Hazard factors ---
    if rr_sub >= 0.60:
        factors.append(f"very heavy rainfall ({rainfall_mm:.1f} mm/hr)")
    elif rr_sub >= 0.30:
        factors.append(f"significant rainfall ({rainfall_mm:.1f} mm/hr)")

    if cr_sub >= 0.60:
        factors.append(f"high 6-hour cumulative rain ({cumul_rain:.1f} mm)")
    elif cr_sub >= 0.30:
        factors.append(f"moderate 6-hour accumulation ({cumul_rain:.1f} mm)")

    if rl_sub >= 0.50:
        danger = REGION_DANGER_LEVELS.get(area_id, DEFAULT_DANGER_LEVEL)
        factors.append(
            f"river level above danger threshold "
            f"({river_level:.2f} m vs {danger:.1f} m limit)"
        )

    if rt_sub >= 0.70:
        factors.append(f"river is rising rapidly (+{river_trend:.2f} m in 3 hrs)")
    elif rt_sub >= 0.55:
        factors.append("river is rising")
    elif rt_sub <= 0.35:
        factors.append("river is falling (reducing hazard)")

    # --- Structural factors ---
    if vulnerability >= 0.55:
        factors.append("high structural vulnerability")
    elif vulnerability >= 0.40:
        factors.append("moderate structural vulnerability")

    if exposure >= 0.55:
        factors.append("high population exposure")

    # --- Low-risk explanation ---
    if not factors:
        if rainfall_mm < 1.0 and cumul_rain < 5.0:
            factors.append("minimal rainfall")
        if river_trend < 0:
            factors.append("river level falling")
        factors.append("conditions within normal range")

    sentence = "; ".join(factors).capitalize() + "."
    return sentence


# ---------------------------------------------------------------------------
# Data loader — builds AreaObservation objects from climate_history.csv
# ---------------------------------------------------------------------------

def load_latest_observations(
    csv_path: str = CLIMATE_CSV,
    as_of:    Optional[pd.Timestamp] = None,
) -> List[AreaObservation]:
    """
    Read climate_history.csv and return one AreaObservation per region,
    built from the latest available timestamp (or `as_of` if provided).

    The function looks back up to 6 hours to compute:
      - cumulative_rain_6h  (rolling sum)
      - river_trend_3h      (level now minus level 3 hours ago)

    Parameters
    ----------
    csv_path : Path to climate_history.csv.
    as_of    : If given, treat this as "now" (useful for back-testing).
               Defaults to the most recent timestamp in the file.

    Returns
    -------
    List of AreaObservation, one per region.
    """
    df = pd.read_csv(csv_path, parse_dates=["timestamp"])
    df.sort_values(["area_id", "timestamp"], inplace=True)
    df.reset_index(drop=True, inplace=True)

    cutoff = as_of if as_of is not None else df["timestamp"].max()

    observations: List[AreaObservation] = []

    for area_id, group in df.groupby("area_id"):
        # Data up to and including the cutoff timestamp
        hist = group[group["timestamp"] <= cutoff].copy()
        if hist.empty:
            continue

        # Latest row
        latest = hist.iloc[-1]

        # Cumulative rainfall over last 6 hours
        window_start   = cutoff - pd.Timedelta(hours=5)
        window_rows    = hist[hist["timestamp"] >= window_start]
        cumul_rain_6h  = float(window_rows["rainfall_mm"].sum())

        # River trend: level now minus level 3 hours ago
        trend_start    = cutoff - pd.Timedelta(hours=3)
        trend_rows     = hist[hist["timestamp"] <= trend_start]
        if not trend_rows.empty:
            level_3h_ago   = float(trend_rows.iloc[-1]["river_level_m"])
            river_trend_3h = float(latest["river_level_m"]) - level_3h_ago
        else:
            river_trend_3h = 0.0

        obs = AreaObservation(
            area_id                    = str(latest["area_id"]),
            area_name                  = str(latest["area_name"]),
            timestamp                  = latest["timestamp"],
            rainfall_mm                = float(latest["rainfall_mm"]),
            cumulative_rain_6h         = cumul_rain_6h,
            river_level_m              = float(latest["river_level_m"]),
            river_trend_3h             = river_trend_3h,
            temperature_c              = float(latest["temperature_c"]),
            humidity                   = float(latest["humidity"]),
            historical_flood_frequency = float(latest["historical_flood_frequency"]),
            population                 = float(latest["population"]),
            population_density         = float(latest["population_density"]),
            vulnerability_index        = float(latest["vulnerability_index"]),
            road_accessibility         = float(latest["road_accessibility"]),
        )
        observations.append(obs)

    return observations


def run_risk_engine(
    csv_path: str = CLIMATE_CSV,
    as_of:    Optional[pd.Timestamp] = None,
) -> List[RiskResult]:
    """
    End-to-end entry point: load observations → score → return results.

    Parameters
    ----------
    csv_path : Path to climate_history.csv.
    as_of    : Treat this timestamp as "now".  Defaults to latest in file.

    Returns
    -------
    List of RiskResult, sorted descending by risk_score.
    """
    observations = load_latest_observations(csv_path=csv_path, as_of=as_of)
    results      = [calculate_flood_risk(obs) for obs in observations]
    results.sort(key=lambda r: r.risk_score, reverse=True)
    return results
