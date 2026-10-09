"""
train_real.py
=============
Training and evaluation pipeline for the REAL-DATA flood forecast model.

This module is SEPARATE from train.py (which trains the synthetic model).
It trains a RandomForestClassifier on real-world flood labels and
produces honest evaluation metrics.

KEY DIFFERENCES FROM SYNTHETIC TRAINING
----------------------------------------
1. Target is BINARY (flood event yes/no), not continuous (0-100 score)
2. Features come from real data (GPM/ERA5/CWC), not synthetic CSV
3. Evaluation uses classification metrics (precision, recall, F1, PR-AUC)
4. Baseline comparison uses a persistence/climate-normal baseline
5. Model is saved to a SEPARATE file (real_data_model.pkl)
6. Metadata clearly identifies the model as real-data-trained

HONEST EVALUATION
-----------------
- Chronological split (train on earlier, test on later)
- No shuffling
- Test metrics are reported separately from train metrics
- If the test set has too few positive examples, results are flagged
  as inconclusive
- A simple baseline (always predict the majority class, or use
  climate-normal persistence) is compared against the RF model

Run:
    python -m backend.forecasting.train_real
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

if __package__ in (None, ""):
    sys.path.insert(
        0,
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    )

from backend.forecasting.features import MODELS_DIR  # noqa: E402
from backend.forecasting.preprocess import (  # noqa: E402
    REAL_FEATURE_COLUMNS,
    STATIC_FEATURE_COLUMNS,
    TARGET_COLUMN,
    DataQualityReport,
    run_preprocessing_pipeline,
    save_quality_report,
)
from backend.forecasting.target import (  # noqa: E402
    DEFAULT_HORIZON_HOURS,
    FloodThresholdConfig,
    load_threshold_config,
)

# ---------------------------------------------------------------------------
# Model paths (SEPARATE from synthetic model)
# ---------------------------------------------------------------------------
REAL_MODEL_PATH = os.path.join(MODELS_DIR, "real_data_model.pkl")
REAL_METADATA_PATH = os.path.join(MODELS_DIR, "real_data_metadata.json")

# ---------------------------------------------------------------------------
# Hyperparameters
# ---------------------------------------------------------------------------
HYPERPARAMETERS: Dict = {
    "n_estimators": 200,
    "max_depth": 12,
    "min_samples_leaf": 5,
    "class_weight": "balanced",
    "random_state": 42,
    "n_jobs": -1,
}


# ---------------------------------------------------------------------------
# Chronological split (same logic as features.py but for real data)
# ---------------------------------------------------------------------------

def split_chronological_real(
    frame: pd.DataFrame,
    test_ratio: float = 0.2,
    cutoff: Optional[pd.Timestamp] = None,
) -> Tuple[pd.DataFrame, pd.DataFrame, Dict[str, str]]:
    """
    Split the real-data feature frame by TIME.
    Training = earlier period, Test = later period.
    """
    if cutoff is None:
        times = pd.DatetimeIndex(sorted(frame["timestamp"].unique()))
        split_index = int(len(times) * (1.0 - test_ratio))
        split_index = min(max(split_index, 1), len(times) - 1)
        cutoff = times[split_index]
    else:
        cutoff = pd.Timestamp(cutoff)

    train_df = frame[frame["timestamp"] < cutoff].reset_index(drop=True)
    test_df = frame[frame["timestamp"] >= cutoff].reset_index(drop=True)

    if train_df.empty or test_df.empty:
        raise ValueError(
            "Chronological split produced an empty set — check the data range."
        )

    info = {
        "cutoff": str(cutoff),
        "train_start": str(train_df["timestamp"].min()),
        "train_end": str(train_df["timestamp"].max()),
        "test_start": str(test_df["timestamp"].min()),
        "test_end": str(test_df["timestamp"].max()),
        "n_train_rows": str(len(train_df)),
        "n_test_rows": str(len(test_df)),
        "n_train_positive": str(int(train_df[TARGET_COLUMN].sum())),
        "n_test_positive": str(int(test_df[TARGET_COLUMN].sum())),
    }
    return train_df, test_df, info


# ---------------------------------------------------------------------------
# Evaluation metrics for binary classification
# ---------------------------------------------------------------------------

def compute_classification_metrics(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    y_prob: Optional[np.ndarray] = None,
) -> Dict[str, float]:
    """
    Compute classification metrics for binary flood-event prediction.

    Returns a dict with:
      - accuracy, precision, recall, f1
      - pr_auc (if y_prob provided)
      - confusion_matrix (tn, fp, fn, tp)
      - class_balance (pos/neg ratio)
      - n_samples
    """
    from sklearn.metrics import (
        accuracy_score,
        confusion_matrix,
        f1_score,
        precision_score,
        recall_score,
    )

    y_true = np.asarray(y_true, dtype=int)
    y_pred = np.asarray(y_pred, dtype=int)

    metrics: Dict[str, float] = {
        "n_samples": int(len(y_true)),
        "accuracy": round(float(accuracy_score(y_true, y_pred)), 4),
        "precision": round(float(precision_score(y_true, y_pred, zero_division=0)), 4),
        "recall": round(float(recall_score(y_true, y_pred, zero_division=0)), 4),
        "f1": round(float(f1_score(y_true, y_pred, zero_division=0)), 4),
    }

    # Confusion matrix
    cm = confusion_matrix(y_true, y_pred, labels=[0, 1])
    if cm.shape == (2, 2):
        metrics["confusion_matrix"] = {
            "tn": int(cm[0, 0]),
            "fp": int(cm[0, 1]),
            "fn": int(cm[1, 0]),
            "tp": int(cm[1, 1]),
        }

    # PR-AUC (only if probabilities are available and both classes present)
    if y_prob is not None and len(np.unique(y_true)) == 2:
        from sklearn.metrics import average_precision_score
        metrics["pr_auc"] = round(
            float(average_precision_score(y_true, y_prob)), 4
        )

    # Class balance
    n_pos = int(y_true.sum())
    n_neg = int(len(y_true) - n_pos)
    metrics["n_positive"] = n_pos
    metrics["n_negative"] = n_neg
    metrics["class_balance_pos_neg"] = (
        round(n_pos / n_neg, 4) if n_neg > 0 else float("inf")
    )

    return metrics


def compute_baseline_metrics(
    y_true: np.ndarray,
    y_train: np.ndarray,
) -> Dict[str, float]:
    """
    Compute metrics for a simple baseline: predict the training-set
    majority class for all test samples.

    This is a meaningful baseline because it represents "no model" —
    just predicting the most common outcome.
    """
    from sklearn.metrics import (
        accuracy_score,
        f1_score,
        precision_score,
        recall_score,
    )

    # Baseline: predict the majority class from training
    train_pos_rate = float(np.mean(y_train))
    majority_class = 1 if train_pos_rate >= 0.5 else 0
    y_pred_baseline = np.full_like(y_true, majority_class, dtype=int)

    return {
        "strategy": "majority_class_from_train",
        "train_positive_rate": round(train_pos_rate, 4),
        "accuracy": round(float(accuracy_score(y_true, y_pred_baseline)), 4),
        "precision": round(
            float(precision_score(y_true, y_pred_baseline, zero_division=0)), 4
        ),
        "recall": round(
            float(recall_score(y_true, y_pred_baseline, zero_division=0)), 4
        ),
        "f1": round(
            float(f1_score(y_true, y_pred_baseline, zero_division=0)), 4
        ),
    }


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------

def train_real(
    feature_frame: pd.DataFrame,
    quality_report: DataQualityReport,
    test_ratio: float = 0.2,
    verbose: bool = True,
) -> Dict:
    """
    Train, evaluate, and persist the real-data flood forecast model.

    Parameters
    ----------
    feature_frame : Preprocessed feature table with TARGET_COLUMN.
    quality_report : Data quality report from the preprocessing pipeline.
    test_ratio : Fraction of the time period to hold out for testing.
    verbose : Print progress to console.

    Returns
    -------
    Dict with model, metrics, split info, and file paths.
    """
    from sklearn.ensemble import RandomForestClassifier

    if verbose:
        print("=" * 70)
        print("REAL-DATA FLOOD MODEL TRAINING")
        print("=" * 70)

    # Check for critical errors
    if quality_report.validation_errors:
        for err in quality_report.validation_errors:
            if verbose:
                print(f"  ERROR: {err}")
        raise ValueError(
            "Cannot train: critical data errors found. "
            "See quality report for details."
        )

    # Determine available feature columns
    feature_cols = [
        c for c in REAL_FEATURE_COLUMNS + STATIC_FEATURE_COLUMNS
        if c in feature_frame.columns and feature_frame[c].notna().any()
    ]

    if not feature_cols:
        raise ValueError("No feature columns available for training.")

    if verbose:
        print(f"Features   : {len(feature_cols)} available")
        print(f"Rows       : {len(feature_frame):,}")
        print(f"Target     : {TARGET_COLUMN} (binary flood event)")
        print(f"Horizon    : {DEFAULT_HORIZON_HOURS} hours ahead")

    # Chronological split
    train_df, test_df, split_info = split_chronological_real(
        feature_frame, test_ratio=test_ratio
    )

    if verbose:
        print(f"Train      : {split_info['train_start']} -> {split_info['train_end']}")
        print(f"               ({split_info['n_train_rows']} rows, "
              f"{split_info['n_train_positive']} positive)")
        print(f"Test       : {split_info['test_start']} -> {split_info['test_end']}")
        print(f"               ({split_info['n_test_rows']} rows, "
              f"{split_info['n_test_positive']} positive)")

    X_train = train_df[feature_cols]
    y_train = train_df[TARGET_COLUMN].astype(int)
    X_test = test_df[feature_cols]
    y_test = test_df[TARGET_COLUMN].astype(int)

    # Check class balance
    n_train_pos = int(y_train.sum())
    n_test_pos = int(y_test.sum())

    if n_train_pos == 0:
        raise ValueError(
            "No positive examples in training set. "
            "Cannot train a classifier without flood events."
        )

    if n_test_pos < 5:
        if verbose:
            print(f"  WARNING: Only {n_test_pos} positive examples in test set. "
                  f"Results may be inconclusive.")

    # Fit
    model = RandomForestClassifier(**HYPERPARAMETERS)
    model.fit(X_train, y_train)

    # Evaluate
    y_pred = model.predict(X_test)
    y_prob = model.predict_proba(X_test)[:, 1]

    test_metrics = compute_classification_metrics(y_test, y_pred, y_prob)
    train_metrics = compute_classification_metrics(
        y_train, model.predict(X_train), model.predict_proba(X_train)[:, 1]
    )
    baseline_metrics = compute_baseline_metrics(
        y_test.to_numpy(), y_train.to_numpy()
    )

    if verbose:
        print()
        print("TEST METRICS (held-out, later period)")
        print("-" * 40)
        for k, v in test_metrics.items():
            if k != "confusion_matrix":
                print(f"  {k:25s}: {v}")
        if "confusion_matrix" in test_metrics:
            cm = test_metrics["confusion_matrix"]
            print(f"  {'confusion_matrix':25s}: TN={cm['tn']} FP={cm['fp']} "
                  f"FN={cm['fn']} TP={cm['tp']}")
        print()
        print("BASELINE (majority class)")
        print("-" * 40)
        for k, v in baseline_metrics.items():
            print(f"  {k:25s}: {v}")
        print()
        print("TRAIN METRICS (for reference only)")
        print("-" * 40)
        for k, v in train_metrics.items():
            if k != "confusion_matrix":
                print(f"  {k:25s}: {v}")

    # Persist
    os.makedirs(MODELS_DIR, exist_ok=True)
    import joblib
    joblib.dump(model, REAL_MODEL_PATH)

    metadata = {
        "model_type": "RandomForestClassifier",
        "framework": "scikit-learn",
        "model_id": "real_data_model",
        "trained_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "forecast_horizon_hours": DEFAULT_HORIZON_HOURS,
        "target_definition": (
            "future_flood_event = 1 if river stage at T+6h exceeds "
            "documented flood threshold, 0 otherwise"
        ),
        "target_type": "binary_classification",
        "feature_names": list(feature_cols),
        "hyperparameters": {k: v for k, v in HYPERPARAMETERS.items()},
        "split": split_info,
        "n_rows_total": int(len(feature_frame)),
        "test_metrics": test_metrics,
        "train_metrics": train_metrics,
        "baseline_metrics": baseline_metrics,
        "data_sources": [s.get("source_name", "unknown") for s in quality_report.sources],
        "study_region": quality_report.study_region,
        "time_coverage": {
            "start": quality_report.time_start,
            "end": quality_report.time_end,
        },
        "n_locations": quality_report.n_locations,
        "source_data": "REAL-WORLD DATA (GPM IMERG / ERA5 / CWC)",
        "disclaimer": (
            "Trained on real-world historical data. Predictions are "
            "decision-support estimates and must NOT be used for "
            "operational flood forecasting without independent "
            "validation by qualified hydrologists."
        ),
        "data_quality_report": quality_report.to_dict(),
    }

    with open(REAL_METADATA_PATH, "w", encoding="utf-8") as fh:
        json.dump(metadata, fh, indent=2, ensure_ascii=False, default=str)

    if verbose:
        print(f"Model      : {REAL_MODEL_PATH}")
        print(f"Metadata   : {REAL_METADATA_PATH}")
        print("Done.")

    return {
        "model": model,
        "test_metrics": test_metrics,
        "train_metrics": train_metrics,
        "baseline_metrics": baseline_metrics,
        "split": split_info,
        "model_path": REAL_MODEL_PATH,
        "metadata_path": REAL_METADATA_PATH,
        "feature_columns": feature_cols,
    }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """
    Run the full real-data training pipeline:
    1. Load data from ingestion adapters
    2. Preprocess
    3. Train and evaluate
    4. Save model and metadata
    """
    from backend.data.ingest.gpm_imerg import GPMIMERGAdapter
    from backend.data.ingest.era5 import ERA5Adapter
    from backend.data.ingest.cwc import CWCAdapter

    print("Loading data from adapters...")
    adapters = []

    # Try each adapter; skip if data is not available
    for adapter_cls in [GPMIMERGAdapter, ERA5Adapter, CWCAdapter]:
        adapter = adapter_cls()
        try:
            adapter.load()
            adapters.append(adapter)
            print(f"  [OK] {adapter.source_name}")
        except FileNotFoundError as e:
            print(f"  [SKIP] {adapter.source_name}: data not found")
        except Exception as e:
            print(f"  [ERROR] {adapter.source_name}: {e}")

    if not adapters:
        print()
        print("No data sources available. Please download the required data:")
        print()
        print("  1. NASA GPM IMERG precipitation:")
        print("     https://gpm.nasa.gov/data/imerg")
        print("     Requires free Earthdata account: https://urs.earthdata.nasa.gov/")
        print("     Place in: backend/data/real/gpm_imerg/gpm_imerg.csv")
        print()
        print("  2. Copernicus ERA5 weather (optional, adds temperature/humidity):")
        print("     https://cds.climate.copernicus.eu/")
        print("     Place in: backend/data/real/era5/era5.csv")
        print()
        print("  3. CWC river gauge data (REQUIRED for flood labels):")
        print("     https://cwcindia.gov.in/")
        print("     Place in: backend/data/real/cwc/cwc_river_data.csv")
        print()
        print("  4. Flood threshold configuration:")
        print("     Place in: backend/data/real/flood_thresholds.json")
        print()
        print("See backend/data/real/README.md for detailed instructions.")
        sys.exit(1)

    # Load threshold config
    threshold_config = load_threshold_config()

    # Run preprocessing
    print("\nRunning preprocessing pipeline...")
    feature_frame, quality_report = run_preprocessing_pipeline(
        adapters=adapters,
        threshold_config=threshold_config,
        horizon_hours=DEFAULT_HORIZON_HOURS,
        study_region="Madhya Pradesh, India",
    )

    # Save quality report
    report_path = save_quality_report(quality_report)
    print(f"Data quality report saved to: {report_path}")

    # Check for critical errors
    if quality_report.validation_errors:
        print("\nCRITICAL ERRORS PREVENTING TRAINING:")
        for err in quality_report.validation_errors:
            print(f"  - {err}")
        sys.exit(1)

    if quality_report.validation_warnings:
        print("\nWARNINGS:")
        for w in quality_report.validation_warnings:
            print(f"  - {w}")

    # Train
    print()
    result = train_real(feature_frame, quality_report, verbose=True)

    # Print final summary
    print()
    print("=" * 70)
    print("TRAINING COMPLETE")
    print("=" * 70)
    print(f"  Model: {result['model_path']}")
    print(f"  Test F1: {result['test_metrics'].get('f1', 'N/A')}")
    print(f"  Baseline F1: {result['baseline_metrics'].get('f1', 'N/A')}")
    print()
    print("NOTE: These are prototype decision-support estimates.")
    print("They are NOT operational flood forecasts.")
    print("Independent validation by qualified hydrologists is required")
    print("before any real-world use.")


if __name__ == "__main__":
    main()
