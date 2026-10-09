"""
test_real_pipeline.py
=====================
Tests for the real-data ingestion, preprocessing, target, model registry,
and training modules.

Usage (from project root):
    python backend/forecasting/test_real_pipeline.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from backend.data.ingest.base import IngestionAdapter, REQUIRED_COLUMNS  # noqa: E402
from backend.forecasting.target import (  # noqa: E402
    DEFAULT_HORIZON_HOURS,
    FloodThresholdConfig,
    derive_flood_labels,
    load_threshold_config,
    target_summary,
)
from backend.forecasting.preprocess import (  # noqa: E402
    standardize_timestamps,
    validate_coordinates,
    validate_numeric_ranges,
    remove_duplicates,
    build_real_features,
    DataQualityReport,
)
from backend.forecasting.model_registry import (  # noqa: E402
    ModelRegistry,
    ModelType,
)
from backend.forecasting.train_real import (  # noqa: E402
    split_chronological_real,
    compute_classification_metrics,
    compute_baseline_metrics,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_river_data(n_hours=100, n_areas=2, flood_at=None):
    """Create test river data (NOT real-world data, just for unit tests)."""
    areas = ["TEST_A", "TEST_B"][:n_areas]
    rows = []
    rng = np.random.default_rng(42)
    for area in areas:
        for h in range(n_hours):
            ts = pd.Timestamp("2024-07-01", tz="UTC") + pd.Timedelta(hours=h)
            level = 2.0 + 0.5 * np.sin(h / 10.0)
            if flood_at and h in flood_at and area == areas[0]:
                level = 5.0
            rows.append({
                "timestamp": ts,
                "area_id": area,
                "gauge_id": f"GAUGE_{area}",
                "river_level_m": level,
                "rainfall_mm": 1.0 + rng.uniform(0, 5),
                "latitude": 22.7,
                "longitude": 75.8,
                "area_name": f"Test Area {area}",
            })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_required_columns():
    """REQUIRED_COLUMNS includes universal fields; source-specific cols are separate."""
    from backend.data.ingest.base import SOURCE_SPECIFIC_REQUIRED
    assert "timestamp" in REQUIRED_COLUMNS
    assert "area_id" in REQUIRED_COLUMNS
    assert "rainfall_mm" in SOURCE_SPECIFIC_REQUIRED["GPM_IMERG"]
    assert "river_level_m" in SOURCE_SPECIFIC_REQUIRED["CWC_RIVER_GAUGES"]
    print("  [PASS] test_required_columns")


def test_standardize_timestamps():
    """Timestamps are converted to UTC and NaT rows removed."""
    df = pd.DataFrame({
        "timestamp": [
            pd.Timestamp("2024-01-01 00:00:00", tz="Asia/Kolkata"),
            pd.Timestamp("2024-01-01 05:30:00", tz="UTC"),
            pd.NaT,
        ],
        "area_id": ["A", "A", "A"],
        "latitude": [22.0, 22.0, 22.0],
        "longitude": [75.0, 75.0, 75.0],
        "rainfall_mm": [1.0, 2.0, 3.0],
    })
    result = standardize_timestamps(df)
    assert len(result) == 2, f"Expected 2 rows, got {len(result)}"
    assert str(result["timestamp"].dt.tz) == "UTC"
    print("  [PASS] test_standardize_timestamps")


def test_validate_coordinates():
    """Invalid coordinates are removed."""
    df = pd.DataFrame({
        "timestamp": pd.date_range("2024-01-01", periods=4, freq="h", tz="UTC"),
        "area_id": ["A"] * 4,
        "latitude": [22.0, 95.0, -95.0, 23.0],
        "longitude": [75.0, 75.0, 75.0, 185.0],
        "rainfall_mm": [1.0, 2.0, 3.0, 4.0],
    })
    result, warnings = validate_coordinates(df)
    assert len(result) == 1, f"Expected 1 valid row, got {len(result)}"
    assert len(warnings) >= 1
    print("  [PASS] test_validate_coordinates")


def test_validate_numeric_ranges():
    """Out-of-range values are removed."""
    df = pd.DataFrame({
        "timestamp": pd.date_range("2024-01-01", periods=5, freq="h", tz="UTC"),
        "area_id": ["A"] * 5,
        "rainfall_mm": [1.0, -5.0, 2.0, 3.0, 4.0],
        "temperature_c": [30.0, 100.0, 25.0, 28.0, 30.0],
    })
    result, warnings = validate_numeric_ranges(df)
    # Row 1: rainfall -5 (invalid) AND temp 100 (invalid) → dropped once
    # Row 4: rainfall 4.0 (valid), temp 30 (valid) → kept
    # Expected: rows 0, 2, 3, 4 survive (row 1 dropped)
    assert len(result) == 4, f"Expected 4 valid rows, got {len(result)}"
    assert len(warnings) >= 1
    print("  [PASS] test_validate_numeric_ranges")


def test_remove_duplicates():
    """Duplicate (area_id, timestamp) rows are removed."""
    df = pd.DataFrame({
        "timestamp": [
            pd.Timestamp("2024-01-01 00:00:00", tz="UTC"),
            pd.Timestamp("2024-01-01 00:00:00", tz="UTC"),
            pd.Timestamp("2024-01-01 01:00:00", tz="UTC"),
        ],
        "area_id": ["A", "A", "A"],
        "latitude": [22.0, 22.0, 22.0],
        "longitude": [75.0, 75.0, 75.0],
        "rainfall_mm": [1.0, 2.0, 3.0],
    })
    result, n_dups = remove_duplicates(df)
    assert len(result) == 2
    assert n_dups == 1
    print("  [PASS] test_remove_duplicates")


def test_build_real_features():
    """Features are built correctly from real data."""
    df = _make_river_data(n_hours=10, n_areas=1)
    result = build_real_features(df)
    assert "rainfall_last_1h" in result.columns
    assert "rainfall_last_3h" in result.columns
    assert "rainfall_last_6h" in result.columns
    assert "river_level" in result.columns
    expected_3h = df["rainfall_mm"].iloc[0] + df["rainfall_mm"].iloc[1] + df["rainfall_mm"].iloc[2]
    assert abs(result["rainfall_last_3h"].iloc[2] - expected_3h) < 1e-6
    print("  [PASS] test_build_real_features")


def test_derive_flood_labels():
    """Flood labels are derived correctly from river stage + threshold."""
    df = _make_river_data(n_hours=20, n_areas=1, flood_at={10})
    config = FloodThresholdConfig(
        thresholds={"GAUGE_TEST_A": 4.0},
        default_threshold=4.0,
    )
    result = derive_flood_labels(df, config, horizon_hours=6)
    assert "flood_event" in result.columns
    assert "future_flood_event" in result.columns
    assert result["flood_event"].iloc[10] == 1
    assert result["flood_event"].iloc[0] == 0
    assert result["future_flood_event"].iloc[4] == 1
    print("  [PASS] test_derive_flood_labels")


def test_target_leakage_prevention():
    """Features at T do not include information from T+horizon."""
    df = _make_river_data(n_hours=20, n_areas=1)
    config = FloodThresholdConfig(
        thresholds={"GAUGE_TEST_A": 4.0},
    )
    labeled = derive_flood_labels(df, config, horizon_hours=6)
    features = build_real_features(labeled)
    for i in range(5, 15):
        assert abs(features["river_level"].iloc[i] - df["river_level_m"].iloc[i]) < 1e-6, \
            f"Leakage at row {i}"
    print("  [PASS] test_target_leakage_prevention")


def test_chronological_split():
    """Chronological split produces train before test."""
    df = _make_river_data(n_hours=100, n_areas=1)
    config = FloodThresholdConfig(thresholds={"GAUGE_TEST_A": 4.0})
    labeled = derive_flood_labels(df, config, horizon_hours=6)
    labeled = labeled.dropna(subset=["future_flood_event"])

    train, test, info = split_chronological_real(labeled, test_ratio=0.2)
    assert train["timestamp"].max() < test["timestamp"].min()
    assert len(train) > 0
    assert len(test) > 0
    print("  [PASS] test_chronological_split")


def test_classification_metrics():
    """Classification metrics are computed correctly."""
    y_true = np.array([0, 0, 0, 1, 1, 1, 0, 1])
    y_pred = np.array([0, 0, 1, 1, 1, 0, 0, 1])
    y_prob = np.array([0.1, 0.2, 0.6, 0.8, 0.9, 0.3, 0.2, 0.7])

    metrics = compute_classification_metrics(y_true, y_pred, y_prob)
    assert metrics["n_samples"] == 8
    assert 0 <= metrics["accuracy"] <= 1
    assert 0 <= metrics["precision"] <= 1
    assert 0 <= metrics["recall"] <= 1
    assert 0 <= metrics["f1"] <= 1
    assert "confusion_matrix" in metrics
    assert metrics["confusion_matrix"]["tp"] == 3
    assert metrics["n_positive"] == 4
    assert metrics["n_negative"] == 4
    print("  [PASS] test_classification_metrics")


def test_baseline_metrics():
    """Baseline (majority class) metrics are computed."""
    y_true = np.array([0, 0, 0, 0, 1, 1, 0, 1])
    y_train = np.array([0, 0, 0, 0, 0, 1, 0, 0])

    metrics = compute_baseline_metrics(y_true, y_train)
    assert metrics["strategy"] == "majority_class_from_train"
    assert metrics["train_positive_rate"] < 0.5
    assert 0 <= metrics["accuracy"] <= 1
    print("  [PASS] test_baseline_metrics")


def test_model_registry_synthetic_fallback():
    """Registry falls back to synthetic model when real-data model is absent."""
    registry = ModelRegistry()
    status = registry.get_model_status()

    assert "active_model" in status
    assert "models" in status
    assert "warning" in status

    if status["active_model"] == "synthetic_baseline":
        assert status["warning"] is not None
        assert "synthetic" in status["warning"].lower()

    print("  [PASS] test_model_registry_synthetic_fallback")


def test_model_registry_active_model_loads():
    """The active model can be loaded and has a predict method."""
    registry = ModelRegistry()
    model, info = registry.get_active_model()
    assert hasattr(model, "predict"), "Model must have a predict method"
    assert info.model_type in (ModelType.SYNTHETIC, ModelType.REAL_DATA)
    print(f"  [PASS] test_model_registry_active_model_loads (active: {info.model_type.value})")


def test_target_summary():
    """Target summary reports correct counts."""
    df = _make_river_data(n_hours=30, n_areas=1, flood_at={15})
    config = FloodThresholdConfig(thresholds={"GAUGE_TEST_A": 4.0})
    labeled = derive_flood_labels(df, config, horizon_hours=6)
    summary = target_summary(labeled, config, horizon_hours=6)

    assert summary["horizon_hours"] == 6
    assert summary["n_total_rows"] == 30
    assert summary["n_valid_rows"] < 30
    assert summary["n_positive_labels"] >= 0
    assert summary["n_negative_labels"] >= 0
    print("  [PASS] test_target_summary")


def test_load_threshold_config_missing_file():
    """Loading a non-existent threshold config returns empty config."""
    config = load_threshold_config("/nonexistent/path/thresholds.json")
    assert config.thresholds == {}
    assert config.default_threshold is None
    assert "No threshold config found" in config.notes
    print("  [PASS] test_load_threshold_config_missing_file")


def test_load_threshold_config_valid():
    """Loading a valid threshold config parses correctly."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump({
            "thresholds": {"G1": 4.5, "G2": 3.8},
            "default_threshold": 4.0,
            "source": "test",
            "notes": "test config",
        }, f)
        path = f.name

    try:
        config = load_threshold_config(path)
        assert config.thresholds == {"G1": 4.5, "G2": 3.8}
        assert config.default_threshold == 4.0
        assert config.get_threshold("G1") == 4.5
        assert config.get_threshold("UNKNOWN") == 4.0
    finally:
        os.unlink(path)

    print("  [PASS] test_load_threshold_config_valid")


def test_flood_threshold_config_get_threshold():
    """Threshold lookup works for known and unknown gauges."""
    config = FloodThresholdConfig(
        thresholds={"A": 1.0, "B": 2.0},
        default_threshold=5.0,
    )
    assert config.get_threshold("A") == 1.0
    assert config.get_threshold("B") == 2.0
    assert config.get_threshold("C") == 5.0

    config_no_default = FloodThresholdConfig(thresholds={"A": 1.0})
    assert config_no_default.get_threshold("A") == 1.0
    assert config_no_default.get_threshold("C") is None
    print("  [PASS] test_flood_threshold_config_get_threshold")


def test_data_quality_report_to_dict():
    """DataQualityReport serializes to dict correctly."""
    report = DataQualityReport(
        study_region="Test Region",
        total_rows=100,
        valid_rows=90,
        excluded_rows=10,
        exclusion_reasons={"duplicates": 5, "no_future_label": 5},
    )
    d = report.to_dict()
    assert d["study_region"] == "Test Region"
    assert d["total_rows"] == 100
    assert d["valid_rows"] == 90
    assert d["excluded_rows"] == 10
    assert d["exclusion_reasons"]["duplicates"] == 5
    print("  [PASS] test_data_quality_report_to_dict")


def test_no_positive_examples_raises():
    """Training with no positive examples raises ValueError."""
    from backend.forecasting.train_real import train_real

    df = _make_river_data(n_hours=50, n_areas=1)
    config = FloodThresholdConfig(thresholds={"GAUGE_TEST_A": 100.0})
    labeled = derive_flood_labels(df, config, horizon_hours=6)
    labeled = labeled.dropna(subset=["future_flood_event"])
    features = build_real_features(labeled)

    report = DataQualityReport(study_region="test")
    try:
        train_real(features, report, verbose=False)
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "No positive examples" in str(e)
    print("  [PASS] test_no_positive_examples_raises")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_tests() -> int:
    tests = [
        test_required_columns,
        test_standardize_timestamps,
        test_validate_coordinates,
        test_validate_numeric_ranges,
        test_remove_duplicates,
        test_build_real_features,
        test_derive_flood_labels,
        test_target_leakage_prevention,
        test_chronological_split,
        test_classification_metrics,
        test_baseline_metrics,
        test_model_registry_synthetic_fallback,
        test_model_registry_active_model_loads,
        test_target_summary,
        test_load_threshold_config_missing_file,
        test_load_threshold_config_valid,
        test_flood_threshold_config_get_threshold,
        test_data_quality_report_to_dict,
        test_no_positive_examples_raises,
    ]

    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            failed += 1
            print(f"  [FAIL] {t.__name__}: {e}")

    total = passed + failed
    print(f"\n{'=' * 50}")
    print(f"  {passed}/{total} passed, {failed} failed")
    print(f"{'=' * 50}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(run_tests())
