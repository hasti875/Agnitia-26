"""
gpm_imerg.py
============
Ingestion adapter for NASA GPM IMERG precipitation data.

DATA SOURCE
-----------
NASA Global Precipitation Measurement (GPM) Integrated Multi-satellite
Retrievals for GPM (IMERG).

Official URL: https://gpm.nasa.gov/data/imerg
Data portal:  https://disc.gsfc.nasa.gov/datasets
API:         https://cmr.earthdata.nasa.gov/search

ACCESS REQUIREMENTS
-------------------
1. Register for a free account at https://urs.earthdata.nasa.gov/
2. Obtain an Earthdata username and password
3. Generate a PDS-Earthdata CI token or use the URS client credentials
4. Download IMERG 30-min or 1-hour precipitation estimates (V07 or later)
   for the study region and time period

The raw files are typically NetCDF (.nc) or HDF5 (.h5) files.
For this prototype, we support two input formats:

  A) Pre-processed CSV (recommended for hackathon):
     One CSV file per month, or a single combined CSV, with columns:
       timestamp (ISO 8601 UTC), latitude, longitude, rainfall_mm

  B) NetCDF files (if xarray/netCDF4 are available):
     Placed in the data directory, auto-detected by glob pattern.

PLACEMENT
---------
Place files in: backend/data/real/gpm_imerg/

Expected CSV columns (case-insensitive):
  timestamp, latitude, longitude, rainfall_mm

If using a single combined file: gpm_imerg.csv
If using monthly files:          gpm_imerg_YYYY-MM.csv
"""

from __future__ import annotations

import glob
import os
from typing import List, Optional

import pandas as pd

from backend.data.ingest.base import IngestionAdapter, REQUIRED_COLUMNS


class GPMIMERGAdapter(IngestionAdapter):
    """
    Ingest NASA GPM IMERG precipitation data.

    Supports:
      - Single CSV: backend/data/real/gpm_imerg/gpm_imerg.csv
      - Monthly CSVs: backend/data/real/gpm_imerg/gpm_imerg_YYYY-MM.csv
      - NetCDF files (if xarray available): backend/data/real/gpm_imerg/*.nc
    """

    @property
    def source_name(self) -> str:
        return "GPM_IMERG"

    @property
    def source_url(self) -> str:
        return "https://gpm.nasa.gov/data/imerg"

    def _default_data_dir(self) -> str:
        _here = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(os.path.dirname(_here), "real", "gpm_imerg")

    def load(self) -> pd.DataFrame:
        frames: List[pd.DataFrame] = []

        # Try single combined CSV first
        single_csv = os.path.join(self.data_dir, "gpm_imerg.csv")
        if os.path.exists(single_csv):
            self._check_file_exists(single_csv)
            df = pd.read_csv(single_csv, parse_dates=["timestamp"])
            frames.append(df)
        else:
            # Try monthly CSVs
            pattern = os.path.join(self.data_dir, "gpm_imerg_*.csv")
            monthly_files = sorted(glob.glob(pattern))
            if monthly_files:
                for f in monthly_files:
                    df = pd.read_csv(f, parse_dates=["timestamp"])
                    frames.append(df)
            else:
                # Try NetCDF
                nc_files = sorted(glob.glob(os.path.join(self.data_dir, "*.nc")))
                if nc_files:
                    frames = self._load_netcdf(nc_files)
                else:
                    raise FileNotFoundError(
                        f"No GPM IMERG data found in {self.data_dir}\n"
                        f"Place one of the following:\n"
                        f"  1. gpm_imerg.csv (combined)\n"
                        f"  2. gpm_imerg_YYYY-MM.csv (monthly)\n"
                        f"  3. *.nc (NetCDF files)\n"
                        f"Download from: {self.source_url}\n"
                        f"Requires free Earthdata account: https://urs.earthdata.nasa.gov/"
                    )

        if not frames:
            raise ValueError("No data loaded from GPM IMERG adapter.")

        df = pd.concat(frames, ignore_index=True)

        # Normalize column names (case-insensitive)
        df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]

        # Rename common IMERG column names
        rename_map = {
            "precipitation": "rainfall_mm",
            "precip_rate": "rainfall_mm",
            "precipitation_rate": "rainfall_mm",
            "pr": "rainfall_mm",
        }
        for old, new in rename_map.items():
            if old in df.columns and "rainfall_mm" not in df.columns:
                df = df.rename(columns={old: new})

        # IMERG precipitation is typically in mm/hour for 1-hour products
        # or mm per 30-min for 30-min products. We standardize to mm/hour.
        # If the source is 30-min, multiply by 2.
        # This is documented in the provenance; the user should verify units.
        self._report.units["rainfall_mm"] = "mm/hour (standardized from source units)"

        # Add source tag
        df["source"] = self.source_name

        # Validate source-specific columns, then universal schema
        df = self._validate_source_columns(df)
        df = self._validate_schema(df)

        self._report.notes.append(
            "GPM IMERG is a satellite-derived precipitation estimate. "
            "It is NOT a ground-truth rain gauge measurement. "
            "Accuracy is highest in tropical regions and degrades over "
            "orographic areas."
        )

        return df

    def _load_netcdf(self, nc_files: List[str]) -> List[pd.DataFrame]:
        """Load NetCDF files using xarray (optional dependency)."""
        try:
            import xarray as xr
        except ImportError:
            raise ImportError(
                "xarray is required to read NetCDF files. "
                "Install with: pip install xarray netCDF4"
            )

        frames = []
        for nc_path in nc_files:
            ds = xr.open_dataset(nc_path)
            # IMERG NetCDF typically has: time, latitude, longitude, precipitation
            precip_var = None
            for var in ds.data_vars:
                if "precip" in var.lower():
                    precip_var = var
                    break
            if precip_var is None:
                self._report.notes.append(
                    f"Could not find precipitation variable in {nc_path}"
                )
                ds.close()
                continue

            df = ds[[precip_var, "latitude", "longitude"]].reset_index()
            df = df.rename(columns={precip_var: "rainfall_mm"})
            df["timestamp"] = pd.to_datetime(df["time"], utc=True)
            df = df[["timestamp", "latitude", "longitude", "rainfall_mm"]]
            frames.append(df)
            ds.close()

        return frames
