"""
cwc.py
======
Ingestion adapter for Central Water Commission (CWC) / Central Water
Resources (CWR) river gauge data from India.

DATA SOURCE
-----------
The Central Water Commission (CWC), Ministry of Jal Shakti, Government
of India, maintains river gauge stations across India.

Official URLs:
  - CWC portal:       https://cwcindia.gov.in/
  - Flood data:       https://cwcindia.gov.in/flood-data
  - River stage data: https://cwcindia.gov.in/river-stage-data
  - ISIMIP (Interim Secretariat for the International Mekong River
    Commission — not directly applicable but similar format):
    https://www.isimip.org/

For the Narmada / Tapti / Mahanadi basins (relevant to Madhya Pradesh):
  - Narmada:  https://cwcindia.gov.in/narmada
  - Tapti:    https://cwcindia.gov.in/tapti

ACCESS REQUIREMENTS
-------------------
CWC data is publicly available but typically requires:
  1. Manual download from the CWC portal (no API key needed for most data)
  2. Some datasets require a written request to CWC
  3. Data is provided as Excel (.xlsx) or CSV files
  4. River stage data is typically in metres above a local datum

For this prototype, we support:

  A) CSV files (recommended):
     One CSV per gauge station, or a combined CSV.
     Columns: timestamp, gauge_id, river_name, stage_m, area_id

  B) Excel files (.xlsx):
     If openpyxl is available.

PLACEMENT
---------
Place files in: backend/data/real/cwc/

Expected CSV columns (case-insensitive):
  timestamp, gauge_id, river_name, stage_m, area_id

The area_id maps the gauge to one of the 8 study regions.
This mapping is critical and must be defined by the user.
"""

from __future__ import annotations

import glob
import os
from typing import List

import pandas as pd

from backend.data.ingest.base import IngestionAdapter


class CWCAdapter(IngestionAdapter):
    """
    Ingest CWC / CWR river gauge data.

    This adapter provides river level observations which are the
    PRIMARY source for the flood target variable (river stage
    exceedance).

    Supports:
      - CSV: backend/data/real/cwc/cwc_river_data.csv
      - Per-station CSVs: backend/data/real/cwc/gauge_*.csv
      - Excel: backend/data/real/cwc/*.xlsx
    """

    @property
    def source_name(self) -> str:
        return "CWC_RIVER_GAUGES"

    @property
    def source_url(self) -> str:
        return "https://cwcindia.gov.in/"

    def _default_data_dir(self) -> str:
        _here = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(os.path.dirname(_here), "real", "cwc")

    def load(self) -> pd.DataFrame:
        frames: List[pd.DataFrame] = []

        # Try combined CSV
        combined = os.path.join(self.data_dir, "cwc_river_data.csv")
        if os.path.exists(combined):
            df = pd.read_csv(combined)
            frames.append(df)
        else:
            # Try per-station CSVs
            pattern = os.path.join(self.data_dir, "gauge_*.csv")
            station_files = sorted(glob.glob(pattern))
            if station_files:
                for f in station_files:
                    df = pd.read_csv(f)
                    frames.append(df)
            else:
                # Try Excel
                xlsx_files = sorted(glob.glob(os.path.join(self.data_dir, "*.xlsx")))
                if xlsx_files:
                    for f in xlsx_files:
                        try:
                            df = pd.read_excel(f)
                            frames.append(df)
                        except ImportError:
                            raise ImportError(
                                "openpyxl is required to read Excel files. "
                                "Install with: pip install openpyxl"
                            )
                else:
                    raise FileNotFoundError(
                        f"No CWC river gauge data found in {self.data_dir}\n"
                        f"Place one of the following:\n"
                        f"  1. cwc_river_data.csv (combined)\n"
                        f"  2. gauge_*.csv (per-station)\n"
                        f"  3. *.xlsx (Excel files)\n"
                        f"Download from: {self.source_url}\n"
                        f"Data is publicly available; no API key required "
                        f"for most datasets."
                    )

        if not frames:
            raise ValueError("No data loaded from CWC adapter.")

        df = pd.concat(frames, ignore_index=True)
        df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]

        # Rename common CWC column names
        rename_map = {
            "stage": "river_level_m",
            "river_stage": "river_level_m",
            "stage_m": "river_level_m",
            "river_level": "river_level_m",
            "date": "timestamp",
            "datetime": "timestamp",
            "station_id": "gauge_id",
            "station": "gauge_id",
        }
        for old, new in rename_map.items():
            if old in df.columns and new not in df.columns:
                df = df.rename(columns={old: new})

        # Parse timestamps
        if "timestamp" in df.columns:
            df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")

        # Ensure river_level_m is numeric
        if "river_level_m" in df.columns:
            df["river_level_m"] = pd.to_numeric(df["river_level_m"], errors="coerce")

        self._report.units["river_level_m"] = "metres above local gauge datum"

        # CWC data may not have latitude/longitude — these need to be
        # provided by the user in the CSV or via a mapping file.
        # If missing, we'll flag it in the report.
        if "latitude" not in df.columns or "longitude" not in df.columns:
            self._report.notes.append(
                "WARNING: CWC data is missing latitude/longitude columns. "
                "Add these columns to your CSV file, or provide a "
                "gauge_coordinates.csv mapping file in the same directory."
            )
            # Try to load a coordinate mapping
            coord_file = os.path.join(self.data_dir, "gauge_coordinates.csv")
            if os.path.exists(coord_file):
                coords = pd.read_csv(coord_file)
                coords.columns = [c.strip().lower() for c in coords.columns]
                if "gauge_id" in coords.columns and "latitude" in coords.columns:
                    df = df.merge(coords, on="gauge_id", how="left")
                    self._report.notes.append(
                        "Loaded gauge coordinates from gauge_coordinates.csv"
                    )

        # Add source tag
        df["source"] = self.source_name

        # CWC data is the PRIMARY source for flood labels.
        # The flood_event column may be present if the user has annotated
        # flood events, or it can be derived from river_level_m using
        # a threshold (see target.py).
        if "flood_event" not in df.columns:
            df["flood_event"] = None  # to be derived in target.py

        # Validate source-specific columns, then universal schema
        df = self._validate_source_columns(df)
        df = self._validate_schema(df)

        self._report.notes.append(
            "CWC river gauge data provides observed river stages. "
            "This is the PRIMARY source for flood target labels. "
            "Flood events are defined as river stage exceeding a "
            "documented threshold (see target.py for the exact definition)."
        )

        return df
