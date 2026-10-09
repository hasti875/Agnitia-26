"""
predict.py
==========
Phase 4 — INFERENCE only. Loads the pre-trained model and forecasts flood risk
6 hours ahead for every region.

This module NEVER trains anything. The dashboard and scenario simulations
call the same code path (``predict_forecast``) so the model stays frozen.

For each region it returns:

    area_id, area_name, current_risk, predicted_risk, risk_change,
    predicted_risk_level, forecast_horizon_hours

    current_risk    → Phase 3 explainable rule-based score (right now)
    predicted_risk  → RandomForest forecast (6 hours from now)
    risk_change     → predicted_risk − current_risk

Both numbers are 0–100 flood-risk scores on the same synthetic scale, and the
levels use the SAME Phase 3 classification (LOW / MODERATE / HIGH /
VERY HIGH / CRITICAL).

Run:
    .venv\\Scripts\\python.exe -m backend.forecasting.predict
    .venv\\Scripts\\python.exe -m backend.forecasting.predict --json
    .venv\\Scripts\\python.exe -m backend.forecasting.predict --as-of "2024-11-30 18:00:00"
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Dict, List, Optional

import numpy as np

if __package__ in (None, ""):                     # allow direct script runs
    sys.path.insert(
        0,
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    )

from backend.forecasting.features import (         # noqa: E402
    FEATURE_COLUMNS,
    FORECAST_HORIZON_HOURS,
    METADATA_PATH,
    MODEL_PATH,
    latest_feature_rows,
)
from backend.risk import classify_risk, run_risk_engine  # noqa: E402


def _load_model_and_metadata():
    """Load the frozen model + its metadata, with a helpful error if missing."""
    if not os.path.exists(MODEL_PATH) or not os.path.exists(METADATA_PATH):
        raise FileNotFoundError(
            "No trained model found. Train first:\n"
            "  .venv\\Scripts\\python.exe -m backend.forecasting.train"
        )
    import joblib
    with open(METADATA_PATH, "r", encoding="utf-8") as fh:
        metadata = json.load(fh)
    return joblib.load(MODEL_PATH), metadata


def predict_forecast(
    csv_path: Optional[str] = None,
    as_of:    Optional[str] = None,
) -> List[Dict]:
    """
    Forecast flood risk 6 hours ahead for all 8 regions.

    Parameters
    ----------
    csv_path : Optional override of climate_history.csv.
    as_of    : Optional "now" timestamp (default = latest data point).

    Returns
    -------
    List of dicts sorted by predicted_risk (descending).
    """
    from backend.forecasting.features import CLIMATE_CSV

    model, metadata = _load_model_and_metadata()

    # Feature rows available at the cutoff (features only — no target needed).
    rows = latest_feature_rows(csv_path=csv_path or CLIMATE_CSV, as_of=as_of)
    cutoff = rows["timestamp"].max()

    # Phase 3 explainable current risk, evaluated at the same cutoff.
    current = {
        r.area_id: r
        for r in run_risk_engine(csv_path=csv_path or CLIMATE_CSV, as_of=cutoff)
    }

    # Single batched model call — no retraining anywhere in this path.
    X = rows[FEATURE_COLUMNS]
    preds = np.clip(model.predict(X), 0.0, 100.0)

    results: List[Dict] = []
    for (_, row), pred in zip(rows.iterrows(), preds):
        area_id = str(row["area_id"])
        current_risk = current.get(area_id)
        current_score = round(current_risk.risk_score, 2) if current_risk else None

        predicted_score = round(float(pred), 2)
        results.append({
            "area_id":               area_id,
            "area_name":             str(row["area_name"]),
            "current_risk":          current_score,
            "predicted_risk":        predicted_score,
            "risk_change":           (
                round(predicted_score - current_score, 2)
                if current_score is not None else None
            ),
            "predicted_risk_level":  classify_risk(predicted_score),
            "forecast_horizon_hours": int(
                metadata.get("forecast_horizon_hours", FORECAST_HORIZON_HOURS)
            ),
        })

    results.sort(key=lambda r: r["predicted_risk"], reverse=True)
    return results


def _print_table(results: List[Dict], as_of) -> None:
    print("=" * 82)
    print(f"FLOOD-RISK FORECAST - {FORECAST_HORIZON_HOURS} HOURS AHEAD  "
          f"(as of {as_of})")
    print("=" * 82)
    print(f"{'#':<3} {'Area':<12} {'Current':>8} {'Predicted':>10} "
          f"{'Change':>8}  {'Level':<11}")
    print("-" * 82)
    for i, r in enumerate(results, start=1):
        change = r["risk_change"]
        arrow = "+" if change is not None and change > 0 else ""
        print(
            f"{i:<3} {r['area_name']:<12} "
            f"{r['current_risk']:>8.2f} "
            f"{r['predicted_risk']:>10.2f} "
            f"{arrow}{change:>7.2f}  "
            f"{r['predicted_risk_level']:<11}"
        )
    print("-" * 82)
    print("current_risk = Phase 3 rule-based score | predicted_risk = "
          "RandomForest forecast")
    print("SYNTHETIC DATA - prototype demonstration only.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Predict flood risk 6h ahead.")
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    parser.add_argument("--as-of", default=None,
                        help='Cutoff timestamp, e.g. "2024-11-30 18:00:00".')
    args = parser.parse_args()

    results = predict_forecast(as_of=args.as_of)

    if args.json:
        print(json.dumps(results, indent=2, ensure_ascii=False))
    else:
        _print_table(results, as_of=args.as_of or "latest available data")


if __name__ == "__main__":
    main()
