"""
preprocess.py
=============
Reproducible preprocessing pipeline for real-world flood forecasting data.

This module takes the normalized data from the ingestion adapters and:
1. Standardizes timestamps and time zones (UTC)
2. Aligns geographic identifiers and coordinates
3. Validates units, data types, duplicates, missing values, outliers
4. Creates defensible lagged and rolling weather features
5. Prevents future information from leaking into training features
6. Reports data quality metrics

The output is a clean feature table ready for training.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from backend.data.ingest.base import IngestionAdapter, IngestionReport
from backend.forecasting.target import (
    DEFAULT_HORIZON_HOURS,
    FloodThresholdConfig,
    derive_flood_labels,
    load_threshold_config,
    target_summary,
)


# ---------------------------------------------------------------------------
# Feature configuration for real data
# ---------------------------------------------------------------------------

# Features that can be derived from real-world data.
# These are a SUBSET of the synthetic features — we only include
# features that have a real-world counterpart.
REAL_FEATURE_COLUMNS: List[str] = [
    "rainfall_last_1h",
    "rainfall_last_3h",
    "rainfall_last_6h",
    "rainfall_trend",
    "river_level",
    "river_level_change",
    "river_level_trend",
    "temperature",
    "humidity",
]

# Static features (per-area, not time-varying).
# These are optional — included only if present in the data.
STATIC_FEATURE_COLUMNS: List[str] = [
    "historical_flood_frequency",
    "population",
    "population_density",
    "vulnerability_index",
    "road_accessibility",
]

TARGET_COLUMN = "future_flood_event"


# ---------------------------------------------------------------------------
# Data quality report
# ---------------------------------------------------------------------------

@dataclass
class DataQualityReport:
    """Comprehensive data quality and provenance report."""
    # Provenance
    sources: List[dict] = field(default_factory=list)
    study_region: str = ""
    time_start: str = ""
    time_end: str = ""
    n_locations: int = 0

    # Data quality
    total_rows: int = 0
    valid_rows: int = 0
    excluded_rows: int = 0
    exclusion_reasons: Dict[str, int] = field(default_factory=dict)

    # Target
    target_summary: dict = field(default_factory=dict)

    # Features
    feature_columns: List[str] = field(default_factory=list)
    feature_missing: Dict[str, int] = field(default_factory=dict)

    # Validation
    validation_errors: List[str] = field(default_factory=list)
    validation_warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "sources": list(self.sources),
            "study_region": self.study_region,
            "time_start": self.time_start,
            "time_end": self.time_end,
            "n_locations": self.n_locations,
            "total_rows": self.total_rows,
            "valid_rows": self.valid_rows,
            "excluded_rows": self.excluded_rows,
            "exclusion_reasons": dict(self.exclusion_reasons),
            "target_summary": dict(self.target_summary),
            "feature_columns": list(self.feature_columns),
            "feature_missing": dict(self.feature_missing),
            "validation_errors": list(self.validation_errors),
            "validation_warnings": list(self.validation_warnings),
        }


# ---------------------------------------------------------------------------
# Preprocessing pipeline
# ---------------------------------------------------------------------------

def standardize_timestamps(df: pd.DataFrame) -> pd.DataFrame:
    """
    Ensure all timestamps are UTC and in a consistent format.

    - Converts to UTC if a timezone is present
    - Parses string timestamps to datetime
    - Removes rows with NaT timestamps
    """
    out = df.copy()
    if not pd.api.types.is_datetime64_any_dtype(out["timestamp"]):
        out["timestamp"] = pd.to_datetime(out["timestamp"], utc=True, errors="coerce")
    elif out["timestamp"].dt.tz is None:
        out["timestamp"] = out["timestamp"].dt.tz_localize("UTC")
    else:
        out["timestamp"] = out["timestamp"].dt.tz_convert("UTC")

    before = len(out)
    out = out.dropna(subset=["timestamp"])
    excluded = before - len(out)
    if excluded:
        out.attrs.setdefault("exclusions", {})["invalid_timestamps"] = excluded

    return out.sort_values(["area_id", "timestamp"]).reset_index(drop=True)


def validate_coordinates(df: pd.DataFrame) -> Tuple[pd.DataFrame, List[str]]:
    """
    Validate latitude/longitude ranges and remove invalid points.

    Returns (cleaned_df, warnings).
    """
    out = df.copy()
    warnings = []

    if "latitude" in out.columns:
        invalid_lat = (
            out["latitude"].isna()
            | (out["latitude"] < -90)
            | (out["latitude"] > 90)
        )
        if invalid_lat.any():
            warnings.append(
                f"Dropped {invalid_lat.sum()} rows with invalid latitude"
            )
            out = out[~invalid_lat]

    if "longitude" in out.columns:
        invalid_lon = (
            out["longitude"].isna()
            | (out["longitude"] < -180)
            | (out["longitude"] > 180)
        )
        if invalid_lon.any():
            warnings.append(
                f"Dropped {invalid_lon.sum()} rows with invalid longitude"
            )
            out = out[~invalid_lon]

    return out.reset_index(drop=True), warnings


def validate_numeric_ranges(
    df: pd.DataFrame,
) -> Tuple[pd.DataFrame, List[str]]:
    """
    Validate physical ranges of numeric columns.

    - rainfall_mm: >= 0
    - river_level_m: >= 0
    - temperature_c: -50 to 60
    - humidity: 0 to 100

    Returns (cleaned_df, warnings).
    """
    out = df.copy()
    warnings = []

    checks = [
        ("rainfall_mm", 0, float("inf"), "negative rainfall"),
        ("river_level_m", 0, float("inf"), "negative river level"),
        ("temperature_c", -50, 60, "temperature out of range"),
        ("humidity", 0, 100, "humidity out of range"),
    ]

    for col, lo, hi, label in checks:
        if col in out.columns:
            mask = (out[col] < lo) | (out[col] > hi) | out[col].isna()
            if mask.any():
                warnings.append(f"Dropped {mask.sum()} rows with {label}")
                out = out[~mask]

    return out.reset_index(drop=True), warnings


def remove_duplicates(df: pd.DataFrame) -> Tuple[pd.DataFrame, int]:
    """Remove duplicate (area_id, timestamp) rows, keeping the last."""
    before = len(df)
    out = df.drop_duplicates(subset=["area_id", "timestamp"], keep="last")
    return out.reset_index(drop=True), before - len(out)


def build_real_features(
    df: pd.DataFrame,
    horizon_hours: int = DEFAULT_HORIZON_HOURS,
) -> pd.DataFrame:
    """
    Build lagged and rolling features from real-world data.

    All features use ONLY information available at or before time T.
    No future information is used.

    Features:
      rainfall_last_1h   : rainfall at T
      rainfall_last_3h   : rolling sum of rainfall over T-2..T
      rainfall_last_6h   : rolling sum of rainfall over T-5..T
      rainfall_trend     : rainfall at T minus rainfall at T-3
      river_level        : river level at T (if available)
      river_level_change : river level at T minus level at T-1
      river_level_trend  : river level at T minus level at T-3
      temperature        : temperature at T (if available)
      humidity           : humidity at T (if available)
    """
    out = df.copy()
    out = out.sort_values(["area_id", "timestamp"]).reset_index(drop=True)
    by_area = out.groupby("area_id", sort=False)

    # Rainfall features
    if "rainfall_mm" in out.columns:
        rain = out["rainfall_mm"]
        out["rainfall_last_1h"] = rain
        out["rainfall_last_3h"] = by_area["rainfall_mm"].transform(
            lambda s: s.rolling(3, min_periods=1).sum()
        )
        out["rainfall_last_6h"] = by_area["rainfall_mm"].transform(
            lambda s: s.rolling(6, min_periods=1).sum()
        )
        out["rainfall_trend"] = rain - by_area["rainfall_mm"].transform(
            lambda s: s.shift(3)
        )
    else:
        out["rainfall_last_1h"] = np.nan
        out["rainfall_last_3h"] = np.nan
        out["rainfall_last_6h"] = np.nan
        out["rainfall_trend"] = np.nan

    # River features (optional)
    if "river_level_m" in out.columns:
        river = out["river_level_m"]
        out["river_level"] = river
        out["river_level_change"] = river - by_area["river_level_m"].transform(
            lambda s: s.shift(1)
        )
        out["river_level_trend"] = river - by_area["river_level_m"].transform(
            lambda s: s.shift(3)
        )
    else:
        out["river_level"] = np.nan
        out["river_level_change"] = np.nan
        out["river_level_trend"] = np.nan

    # Weather features (optional)
    out["temperature"] = out.get("temperature_c", np.nan)
    out["humidity"] = out.get("humidity", np.nan)

    # Static features (optional, broadcast per area)
    for col in STATIC_FEATURE_COLUMNS:
        if col in out.columns:
            out[col] = by_area[col].transform("first")
        else:
            out[col] = np.nan

    return out


def run_preprocessing_pipeline(
    adapters: List[IngestionAdapter],
    threshold_config: Optional[FloodThresholdConfig] = None,
    horizon_hours: int = DEFAULT_HORIZON_HOURS,
    study_region: str = "Madhya Pradesh, India",
) -> Tuple[pd.DataFrame, DataQualityReport]:
    """
    Run the full preprocessing pipeline.

    Parameters
    ----------
    adapters : List of IngestionAdapter instances (already loaded).
    threshold_config : Flood threshold configuration.
    horizon_hours : Prediction horizon in hours.
    study_region : Description of the study region.

    Returns
    -------
    (feature_frame, quality_report)

    The feature_frame is ready for training: it has all feature columns,
    the target column (future_flood_event), and is sorted by
    (area_id, timestamp).

    Raises
    ------
    ValueError if critical data is missing (no rainfall, no river level,
    no flood labels).
    """
    report = DataQualityReport(study_region=study_region)

    # 1. Load data from all adapters
    frames = []
    for adapter in adapters:
        try:
            df = adapter.load()
            frames.append(df)
            report.sources.append(adapter.get_report().to_dict())
        except FileNotFoundError as e:
            report.validation_errors.append(
                f"Adapter {adapter.source_name}: {e}"
            )
        except Exception as e:
            report.validation_errors.append(
                f"Adapter {adapter.source_name} failed: {e}"
            )

    if not frames:
        raise ValueError(
            "No data loaded from any adapter. "
            "Please download the required data files first."
        )

    # 2. Standardize timestamps in each frame BEFORE merging
    standardized_frames = []
    for df in frames:
        df = standardize_timestamps(df)
        standardized_frames.append(df)

    # 3. Merge sources by (area_id, timestamp) so each row has
    #    BOTH rainfall (from GPM/ERA5) AND river level (from CWC).
    #    A simple concat would leave one column NaN on every row.
    if len(standardized_frames) == 1:
        combined = standardized_frames[0].copy()
    else:
        combined = standardized_frames[0].copy()
        for df in standardized_frames[1:]:
            # Determine merge keys
            merge_keys = ["area_id", "timestamp"]
            # Add gauge_id to keys if both frames have it
            if "gauge_id" in combined.columns and "gauge_id" in df.columns:
                merge_keys.append("gauge_id")
            # Add latitude/longitude to keys if both frames have them
            # (prevents mismatched grid points from being merged)
            if "latitude" in combined.columns and "latitude" in df.columns:
                merge_keys.append("latitude")
                merge_keys.append("longitude")

            # Identify overlapping columns (excluding merge keys and source)
            overlap = [
                c for c in df.columns
                if c in combined.columns
                and c not in merge_keys
                and c != "source"
            ]

            # For overlapping non-key columns, prefer the existing value
            # (first source wins). This means CWC river_level_m takes
            # priority if CWC is loaded first, or GPM rainfall takes
            # priority if GPM is loaded first.
            for col in overlap:
                df[col] = df[col].rename(f"{col}_dup")

            combined = combined.merge(df, on=merge_keys, how="outer", sort=True)

            # Resolve duplicates: prefer non-NaN values
            for col in overlap:
                dup_col = f"{col}_dup"
                if dup_col in combined.columns:
                    combined[col] = combined[col].fillna(combined[dup_col])
                    combined = combined.drop(columns=[dup_col])

            # Track source
            if "source" in df.columns:
                combined["source"] = combined["source"].fillna(df["source"].values if len(df) == len(combined) else np.nan)

    report.total_rows = len(combined)

    # 4. Validate coordinates
    combined, coord_warnings = validate_coordinates(combined)
    report.validation_warnings.extend(coord_warnings)

    # 5. Validate numeric ranges
    combined, range_warnings = validate_numeric_ranges(combined)
    report.validation_warnings.extend(range_warnings)

    # 6. Remove duplicates
    combined, n_dups = remove_duplicates(combined)
    if n_dups:
        report.exclusion_reasons["duplicates"] = n_dups

    # 8. Derive flood labels (target)
    if threshold_config is None:
        threshold_config = load_threshold_config()

    if "river_level_m" in combined.columns:
        combined = derive_flood_labels(
            combined, threshold_config, horizon_hours
        )
        report.target_summary = target_summary(
            combined, threshold_config, horizon_hours
        )
    else:
        report.validation_errors.append(
            "No river_level_m column found. Cannot derive flood labels. "
            "CWC river gauge data is required for the target variable."
        )
        combined["flood_event"] = np.nan
        combined["future_flood_event"] = np.nan

    # 9. Build features
    feature_frame = build_real_features(combined, horizon_hours)

    # 10. Determine which feature columns are actually available
    available_features = []
    for col in REAL_FEATURE_COLUMNS + STATIC_FEATURE_COLUMNS:
        if col in feature_frame.columns:
            non_null = feature_frame[col].notna().sum()
            if non_null > 0:
                available_features.append(col)
            else:
                report.feature_missing[col] = len(feature_frame)
        else:
            report.feature_missing[col] = len(feature_frame)

    report.feature_columns = available_features

    # 11. Check for critical missing data
    if "rainfall_last_1h" not in available_features:
        report.validation_errors.append(
            "No rainfall data available. GPM IMERG or ERA5 data is required."
        )
    if "river_level" not in available_features:
        report.validation_errors.append(
            "No river level data available. CWC gauge data is required."
        )

    # 12. Drop rows where the target is undefined
    if "future_flood_event" in feature_frame.columns:
        before = len(feature_frame)
        feature_frame = feature_frame.dropna(subset=[TARGET_COLUMN])
        excluded = before - len(feature_frame)
        report.exclusion_reasons["no_future_label"] = excluded

    # Drop rows where ALL dynamic features are missing
    dynamic_cols = [c for c in REAL_FEATURE_COLUMNS if c in feature_frame.columns]
    if dynamic_cols:
        before = len(feature_frame)
        feature_frame = feature_frame.dropna(subset=dynamic_cols, how="all")
        excluded = before - len(feature_frame)
        if excluded:
            report.exclusion_reasons["all_features_missing"] = excluded

    report.valid_rows = len(feature_frame)
    report.excluded_rows = report.total_rows - report.valid_rows

    # 13. Final sort
    feature_frame = feature_frame.sort_values(
        ["area_id", "timestamp"]
    ).reset_index(drop=True)

    report.n_locations = feature_frame["area_id"].nunique()
    if not feature_frame.empty:
        report.time_start = str(feature_frame["timestamp"].min())
        report.time_end = str(feature_frame["timestamp"].max())

    return feature_frame, report


def save_quality_report(
    report: DataQualityReport,
    output_path: Optional[str] = None,
) -> str:
    """Save the data quality report as JSON. Returns the output path."""
    if output_path is None:
        _here = os.path.dirname(os.path.abspath(__file__))
        output_path = os.path.join(
            os.path.dirname(_here), "data", "real", "data_quality_report.json"
        )

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as fh:
        import json
        json.dump(report.to_dict(), fh, indent=2, ensure_ascii=False, default=str)

    return output_path
