"""
era5.py
=======
Ingestion adapter for Copernicus ERA5 reanalysis weather data.

DATA SOURCE
-----------
European Centre for Medium-Range Weather Forecasts (ECMWF) ERA5
reanalysis, distributed by the Copernicus Climate Change Service (C3S).

Official URL: https://cds.climate.copernicus.eu/
Dataset:      https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels

ACCESS REQUIREMENTS
-------------------
1. Register for a free account at https://cds.climate.copernicus.eu/
2. Accept the ERA5 data license
3. Download via CDS API (requires API key) or via the web interface
4. Request variables:
   - total_precipitation (tp)        → rainfall
   - 2m_temperature (t2m)           → temperature
   - relative_humidity_2m (r)       → humidity
   - 10m_u_component_of_wind (u10)  → optional
   - 10m_v_component_of_wind (v10)  → optional

The CDS API returns NetCDF files. For this prototype, we support:

  A) Pre-processed CSV (recommended for hackathon):
     One CSV file with columns:
       timestamp (ISO 8601 UTC), latitude, longitude,
       rainfall_mm, temperature_c, humidity

  B) NetCDF files (if xarray/netCDF4 are available)

PLACEMENT
---------
Place files in: backend/data/real/era5/

Expected CSV columns (case-insensitive):
  timestamp, latitude, longitude, rainfall_mm, temperature_c, humidity
"""

from __future__ import annotations

import glob
import os
from typing import List

import pandas as pd

from backend.data.ingest.base import IngestionAdapter


class ERA5Adapter(IngestionAdapter):
    """
    Ingest Copernicus ERA5 reanalysis weather data.

    Supports:
      - Single CSV: backend/data/real/era5/era5.csv
      - Monthly CSVs: backend/data/real/era5/era5_YYYY-MM.csv
      - NetCDF files (if xarray available): backend/data/real/era5/*.nc
    """

    @property
    def source_name(self) -> str:
        return "ERA5"

    @property
    def source_url(self) -> str:
        return "https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels"

    def _default_data_dir(self) -> str:
        _here = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(os.path.dirname(_here), "real", "era5")

    def load(self) -> pd.DataFrame:
        frames: List[pd.DataFrame] = []

        single_csv = os.path.join(self.data_dir, "era5.csv")
        if os.path.exists(single_csv):
            df = pd.read_csv(single_csv, parse_dates=["timestamp"])
            frames.append(df)
        else:
            pattern = os.path.join(self.data_dir, "era5_*.csv")
            monthly_files = sorted(glob.glob(pattern))
            if monthly_files:
                for f in monthly_files:
                    df = pd.read_csv(f, parse_dates=["timestamp"])
                    frames.append(df)
            else:
                nc_files = sorted(glob.glob(os.path.join(self.data_dir, "*.nc")))
                if nc_files:
                    frames = self._load_netcdf(nc_files)
                else:
                    raise FileNotFoundError(
                        f"No ERA5 data found in {self.data_dir}\n"
                        f"Place one of the following:\n"
                        f"  1. era5.csv (combined)\n"
                        f"  2. era5_YYYY-MM.csv (monthly)\n"
                        f"  3. *.nc (NetCDF files)\n"
                        f"Download from: {self.source_url}\n"
                        f"Requires free C3S account: https://cds.climate.copernicus.eu/"
                    )

        if not frames:
            raise ValueError("No data loaded from ERA5 adapter.")

        df = pd.concat(frames, ignore_index=True)
        df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]

        # Rename ERA5 variable names to common schema
        rename_map = {
            "total_precipitation": "rainfall_mm",
            "tp": "rainfall_mm",
            "2m_temperature": "temperature_c",
            "t2m": "temperature_c",
            "relative_humidity_2m": "humidity",
            "r": "humidity",
        }
        for old, new in rename_map.items():
            if old in df.columns and new not in df.columns:
                df = df.rename(columns={old: new})

        # ERA5 total_precipitation is in metres (not mm) — convert
        if "rainfall_mm" in df.columns:
            # Heuristic: if values are all < 0.1, they're likely in metres
            if df["rainfall_mm"].max() < 0.1:
                df["rainfall_mm"] = df["rainfall_mm"] * 1000.0
                self._report.units["rainfall_mm"] = "mm/hour (converted from metres)"
            else:
                self._report.units["rainfall_mm"] = "mm/hour"

        # ERA5 temperature is in Kelvin — convert to Celsius
        if "temperature_c" in df.columns:
            if df["temperature_c"].min() > 200:  # likely Kelvin
                df["temperature_c"] = df["temperature_c"] - 273.15
                self._report.units["temperature_c"] = "Celsius (converted from Kelvin)"
            else:
                self._report.units["temperature_c"] = "Celsius"

        # ERA5 humidity is a fraction (0-1) — convert to percent
        if "humidity" in df.columns:
            if df["humidity"].max() <= 1.0:
                df["humidity"] = df["humidity"] * 100.0
                self._report.units["humidity"] = "percent (converted from fraction)"
            else:
                self._report.units["humidity"] = "percent"

        df["source"] = self.source_name
        df = self._validate_source_columns(df)
        df = self._validate_schema(df)

        self._report.notes.append(
            "ERA5 is a reanalysis product combining model output with "
            "observations. It is NOT direct measurement. Spatial resolution "
            "is ~31 km (0.25°). Values are gridded estimates, not point "
            "measurements."
        )

        return df

    def _load_netcdf(self, nc_files: List[str]) -> List[pd.DataFrame]:
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
            cols = []
            rename = {}
            for var, target in [
                ("tp", "rainfall_mm"),
                ("t2m", "temperature_c"),
                ("r", "humidity"),
            ]:
                if var in ds:
                    cols.append(var)
                    rename[var] = target
            if not cols:
                ds.close()
                continue
            df = ds[cols + ["latitude", "longitude"]].reset_index()
            df = df.rename(columns=rename)
            df["timestamp"] = pd.to_datetime(df["time"], utc=True)
            keep = ["timestamp", "latitude", "longitude"] + list(rename.values())
            df = df[[c for c in keep if c in df.columns]]
            frames.append(df)
            ds.close()
        return frames
