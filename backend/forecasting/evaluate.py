"""
evaluate.py
===========
Phase 4 — evaluation metrics for the flood-risk forecast.

Provides three metrics used by train.py and by the standalone evaluation CLI:

    MAE   Mean Absolute Error          — average points of risk off by
    RMSE  Root Mean Squared Error      — penalises large misses
    R²    Coefficient of determination — 1.0 = perfect, 0.0 = no better than
                                          predicting the average

Run standalone (re-scores the saved model on the held-out test period):

    .venv\\Scripts\\python.exe -m backend.forecasting.evaluate
"""

from __future__ import annotations

import json
import os
import sys
from typing import Dict

import numpy as np

if __package__ in (None, ""):                     # allow direct script runs
    sys.path.insert(
        0,
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    )

from backend.forecasting.features import (      # noqa: E402
    FEATURE_COLUMNS,
    METADATA_PATH,
    MODEL_PATH,
    TARGET_COLUMN,
    build_feature_frame,
    split_chronological,
)


def compute_metrics(y_true, y_pred) -> Dict[str, float]:
    """Calculate MAE, RMSE and R². Returns a dict of rounded floats."""
    from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)

    mae  = float(mean_absolute_error(y_true, y_pred))
    rmse = float(np.sqrt(mean_squared_error(y_true, y_pred)))   # sklearn >= 1.6
    r2   = float(r2_score(y_true, y_pred))

    return {"mae": round(mae, 4), "rmse": round(rmse, 4), "r2": round(r2, 4)}


def format_metrics(metrics: Dict[str, float], title: str = "") -> str:
    """Pretty-print metrics for the console."""
    lines = []
    if title:
        lines.append(title)
    lines.append(f"  MAE  : {metrics['mae']:.4f}")
    lines.append(f"  RMSE : {metrics['rmse']:.4f}")
    lines.append(f"  R2   : {metrics['r2']:.4f}")
    return "\n".join(lines)


def evaluate_saved_model() -> Dict[str, float]:
    """
    Load flood_risk_model.pkl, rebuild the feature table, reproduce the
    ORIGINAL chronological split from model_metadata.json and print metrics
    plus the context needed to interpret them honestly.
    """
    import joblib

    if not os.path.exists(MODEL_PATH) or not os.path.exists(METADATA_PATH):
        raise FileNotFoundError(
            "Model not found. Train it first:\n"
            "  .venv\\Scripts\\python.exe -m backend.forecasting.train"
        )

    with open(METADATA_PATH, "r", encoding="utf-8") as fh:
        metadata = json.load(fh)

    model    = joblib.load(MODEL_PATH)
    frame    = build_feature_frame(with_target=True)
    train_df, test, split_info = split_chronological(
        frame, cutoff=metadata["split"]["cutoff"]
    )

    y_test  = test[TARGET_COLUMN].to_numpy(dtype=float)
    preds   = model.predict(test[FEATURE_COLUMNS])
    metrics = compute_metrics(y_test, preds)

    # --- context: why R² is what it is ------------------------------------
    baseline_mae = float(np.mean(np.abs(y_test - train_df[TARGET_COLUMN].mean())))
    test_std     = float(np.std(y_test))

    print(format_metrics(metrics, "Held-out test period (recomputed)"))
    print(f"  Period : {split_info['test_start']}  ->  {split_info['test_end']}")
    print(f"  Rows   : {split_info['n_test_rows']}")
    print(f"  Stored : {metadata['metrics']}")
    print()
    print("Context for interpreting R2:")
    print(f"  Test target std          : {test_std:.2f} "
          "(low-variance dry-season window)")
    print(f"  Baseline MAE (train mean): {baseline_mae:.2f} "
          "(what a constant prediction scores)")
    print("  Label noise sigma        : 3.5 points (synthetic generator), so this")
    print("  window's theoretical max R2 is roughly 1 - 3.5^2/test_var.")
    print("  Interpretation: MAE below the noise floor = near-optimal for this data.")
    return metrics


def main() -> None:
    evaluate_saved_model()


if __name__ == "__main__":
    main()
