"""
base.py
=======
Abstract base class for data ingestion adapters.

Each adapter is responsible for:
1. Locating and reading raw data files (CSV, NetCDF, etc.)
2. Normalizing to the common schema defined in REQUIRED_COLUMNS
3. Validating the data (timestamps, coordinates, units, missing values)
4. Returning a clean, sorted DataFrame ready for feature engineering

The common schema ensures that the forecasting pipeline does not need
to know which specific source provided the data.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import pandas as pd


# ---------------------------------------------------------------------------
# Common output schema
# ---------------------------------------------------------------------------

# Universal columns that EVERY adapter must produce.
# These are the minimum fields needed to align data across sources.
REQUIRED_COLUMNS: List[str] = [
    "timestamp",          # pd.Timestamp, UTC
    "area_id",            # str, stable identifier for the location
]

# Columns that are REQUIRED for specific source types but not universal.
# Each adapter validates its own source-specific columns.
SOURCE_SPECIFIC_REQUIRED: Dict[str, List[str]] = {
    "GPM_IMERG": ["latitude", "longitude", "rainfall_mm"],
    "ERA5": ["latitude", "longitude", "rainfall_mm"],
    "CWC_RIVER_GAUGES": ["gauge_id", "river_level_m"],
}

# Optional columns (used if present):
OPTIONAL_COLUMNS: List[str] = [
    "area_name",          # str, human-readable name
    "latitude",           # float, WGS84
    "longitude",          # float, WGS84
    "rainfall_mm",        # float, mm per hour
    "river_level_m",      # float, metres above datum
    "temperature_c",      # float, Celsius
    "humidity",           # float, percent
    "flood_event",        # int, 0 or 1 (observed flood label)
    "river_gauge_id",     # str, identifier of the gauge station
    "source",             # str, which adapter produced this row
]


@dataclass
class IngestionReport:
    """Summary of what was ingested and what was excluded."""
    source_name: str
    source_url: str
    access_date: str
    total_rows_read: int = 0
    total_rows_valid: int = 0
    rows_excluded: int = 0
    exclusion_reasons: Dict[str, int] = field(default_factory=dict)
    n_locations: int = 0
    time_start: Optional[str] = None
    time_end: Optional[str] = None
    units: Dict[str, str] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "source_name": self.source_name,
            "source_url": self.source_url,
            "access_date": self.access_date,
            "total_rows_read": self.total_rows_read,
            "total_rows_valid": self.total_rows_valid,
            "rows_excluded": self.rows_excluded,
            "exclusion_reasons": dict(self.exclusion_reasons),
            "n_locations": self.n_locations,
            "time_start": self.time_start,
            "time_end": self.time_end,
            "units": dict(self.units),
            "notes": list(self.notes),
        }


class IngestionAdapter(ABC):
    """
    Abstract base class for all data ingestion adapters.

    Subclasses must implement:
      - load()          → read raw data and return a normalized DataFrame
      - get_report()    → return an IngestionReport describing the data
    """

    def __init__(self, data_dir: Optional[str] = None) -> None:
        self.data_dir = data_dir or self._default_data_dir()
        self._report = IngestionReport(
            source_name=self.source_name,
            source_url=self.source_url,
            access_date=pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d"),
        )

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Short identifier, e.g. 'GPM_IMERG'."""

    @property
    @abstractmethod
    def source_url(self) -> str:
        """Official URL for the data source."""

    @abstractmethod
    def _default_data_dir(self) -> str:
        """Default directory where raw files are expected."""

    @abstractmethod
    def load(self) -> pd.DataFrame:
        """
        Load and normalize the raw data.

        Returns
        -------
        DataFrame sorted by (area_id, timestamp) with at least
        REQUIRED_COLUMNS present. All timestamps are UTC.

        Raises
        ------
        FileNotFoundError if the expected files do not exist.
        ValueError if the data cannot be normalized to the schema.
        """

    def get_report(self) -> IngestionReport:
        """Return the ingestion report (populated during load())."""
        return self._report

    # ------------------------------------------------------------------
    # Shared validation helpers
    # ------------------------------------------------------------------

    def _validate_schema(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Check that universal REQUIRED_COLUMNS are present and correctly typed.
        Drops rows with missing critical fields, recording exclusions.

        Source-specific column validation is done by each adapter
        via _validate_source_columns() before calling this method.
        """
        missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
        if missing:
            raise ValueError(
                f"Adapter '{self.source_name}' produced data missing "
                f"universal required columns: {missing}"
            )

        self._report.total_rows_read = len(df)

        # Ensure timestamp is datetime
        if not pd.api.types.is_datetime64_any_dtype(df["timestamp"]):
            df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")

        # Ensure numeric types for columns that are present
        for col in ["latitude", "longitude", "rainfall_mm", "river_level_m"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        # Track exclusions — only drop rows missing universal fields
        before = len(df)
        df = df.dropna(subset=["timestamp", "area_id"])
        excluded = before - len(df)
        if excluded:
            self._report.rows_excluded += excluded
            self._report.exclusion_reasons["missing_critical_fields"] = (
                self._report.exclusion_reasons.get("missing_critical_fields", 0) + excluded
            )

        # Remove duplicates
        before = len(df)
        df = df.drop_duplicates(subset=["area_id", "timestamp"], keep="last")
        dups = before - len(df)
        if dups:
            self._report.rows_excluded += dups
            self._report.exclusion_reasons["duplicate_timestamps"] = (
                self._report.exclusion_reasons.get("duplicate_timestamps", 0) + dups
            )

        # Sort
        df = df.sort_values(["area_id", "timestamp"]).reset_index(drop=True)

        # Update report
        self._report.total_rows_valid = len(df)
        self._report.n_locations = df["area_id"].nunique()
        if not df.empty:
            self._report.time_start = str(df["timestamp"].min())
            self._report.time_end = str(df["timestamp"].max())

        return df

    def _validate_source_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Validate source-specific required columns. Override in subclasses
        if the default SOURCE_SPECIFIC_REQUIRED mapping is not sufficient.

        Fills missing source-specific columns with NaN so the DataFrame
        has a consistent shape, and records a warning in the report.
        """
        source_cols = SOURCE_SPECIFIC_REQUIRED.get(self.source_name, [])
        for col in source_cols:
            if col not in df.columns:
                df[col] = None
                self._report.notes.append(
                    f"WARNING: Column '{col}' missing from "
                    f"{self.source_name} data. Filled with NaN."
                )
        return df

    def _check_file_exists(self, path: str) -> None:
        if not os.path.exists(path):
            raise FileNotFoundError(
                f"Expected data file not found: {path}\n"
                f"Please download the data and place it at this location.\n"
                f"See the adapter's source_url for download instructions."
            )
