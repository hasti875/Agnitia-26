# Real-World Data Requirements

This directory is where you place real-world data files for the
flood forecasting pipeline. **No data is included in the repository.**
You must download the data from the official sources listed below.

## Directory Structure

```
backend/data/real/
├── gpm_imerg/          # NASA GPM IMERG precipitation
│   └── gpm_imerg.csv   # (or monthly files, or .nc files)
├── era5/               # Copernicus ERA5 weather (optional)
│   └── era5.csv        # (or monthly files, or .nc files)
├── cwc/                # CWC river gauge data (REQUIRED)
│   ├── cwc_river_data.csv
│   └── gauge_coordinates.csv  (optional)
├── flood_thresholds.json   # Flood level thresholds per gauge
└── data_quality_report.json  # (auto-generated)
```

## 1. NASA GPM IMERG Precipitation (REQUIRED)

**Source:** https://gpm.nasa.gov/data/imerg
**Data portal:** https://disc.gsfc.nasa.gov/datasets
**Registration:** Free account at https://urs.earthdata.nasa.gov/

### What to download
- IMERG 1-hour precipitation estimates (V07 or later)
- Study region: Madhya Pradesh, India (approx 21-25°N, 73-78°E)
- Time period: At least 2 years of monsoon seasons (Jun-Nov)
- Resolution: 0.1° × 0.1° (or aggregate to station-level)

### How to prepare
After downloading, create a CSV file with these columns:

| Column | Type | Description |
|--------|------|-------------|
| timestamp | datetime (UTC) | Hourly timestamp |
| latitude | float | WGS84 latitude |
| longitude | float | WGS84 longitude |
| rainfall_mm | float | Precipitation in mm/hour |
| area_id | str | One of: IND, UJJ, DEW, DHA, RAT, MAN, MHO, SEH |

Place at: `backend/data/real/gpm_imerg/gpm_imerg.csv`

### Alternative: NetCDF files
You can also place raw `.nc` files in the directory. The adapter
will read them using xarray (requires `pip install xarray netCDF4`).

## 2. Copernicus ERA5 Weather (OPTIONAL)

**Source:** https://cds.climate.copernicus.eu/
**Dataset:** https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels
**Registration:** Free account at https://cds.climate.copernicus.eu/

### What to download
- ERA5 single-level variables:
  - `total_precipitation` (tp)
  - `2m_temperature` (t2m)
  - `relative_humidity_2m` (r)
- Same study region and time period as GPM IMERG
- Resolution: 0.25° × 0.25°

### How to prepare
Create a CSV with:

| Column | Type | Description |
|--------|------|-------------|
| timestamp | datetime (UTC) | Hourly timestamp |
| latitude | float | WGS84 latitude |
| longitude | float | WGS84 longitude |
| rainfall_mm | float | mm/hour |
| temperature_c | float | Celsius |
| humidity | float | Percent (0-100) |
| area_id | str | Region identifier |

Place at: `backend/data/real/era5/era5.csv`

**Note:** ERA5 is a reanalysis product, not direct measurement.
It adds temperature and humidity features but is not required
if you only have GPM IMERG rainfall data.

## 3. CWC River Gauge Data (REQUIRED for flood labels)

**Source:** https://cwcindia.gov.in/
**Flood data:** https://cwcindia.gov.in/flood-data
**Registration:** None required (public data)

### What to download
- River stage (water level) data for gauge stations in:
  - Narmada basin (Indore, Dewas, Dhar, Ratlam, Mandsaur)
  - Tapti basin (Mhow)
  - Mahanadi basin or nearby (Sehore)
- Time period: Same as GPM IMERG
- Frequency: Hourly or 6-hourly

### How to prepare
Create a CSV with:

| Column | Type | Description |
|--------|------|-------------|
| timestamp | datetime (UTC) | Observation time |
| gauge_id | str | Gauge station identifier |
| river_name | str | River name |
| stage_m | float | Water level in metres above local datum |
| area_id | str | Maps gauge to region (IND, UJJ, etc.) |
| latitude | float | Gauge latitude (WGS84) |
| longitude | float | Gauge longitude (WGS84) |

Place at: `backend/data/real/cwc/cwc_river_data.csv`

### Gauge-to-Area Mapping
You must define which gauge station corresponds to which of the 8
study regions. This is done via the `area_id` column in the CSV.

Example mapping:
| area_id | Region | Suggested Gauge |
|---------|--------|-----------------|
| IND | Indore | Narmada at Indore |
| UJJ | Ujjain | Shipra at Ujjain |
| DEW | Dewas | Narmada at Dewas |
| DHA | Dhar | Narmada at Dhar |
| RAT | Ratlam | Parbhadhi at Ratlam |
| MAN | Mandsaur | Narmada at Mandsaur |
| MHO | Mhow | Tapti at Mhow |
| SEH | Sehore | Narmada at Sehore |

## 4. Flood Threshold Configuration (REQUIRED)

Create `backend/data/real/flood_thresholds.json`:

```json
{
    "thresholds": {
        "IND": 4.5,
        "UJJ": 3.8,
        "DEW": 4.2,
        "DHA": 5.0,
        "RAT": 3.5,
        "MAN": 3.2,
        "MHO": 4.8,
        "SEH": 4.0
    },
    "default_threshold": 4.0,
    "source": "CWC flood level documentation 2023",
    "notes": "Thresholds are the documented flood level (metres above local gauge datum) for each station. When river stage exceeds this level, a flood event is declared."
}
```

**Important:** The threshold values must come from official CWC
documentation for each gauge station. Do NOT make up values.
If you cannot find documented thresholds, you cannot define
flood labels, and supervised training cannot proceed.

## 5. Sample CSV Schemas (Copy-Paste Ready)

### GPM IMERG sample (`gpm_imerg.csv`)

```csv
timestamp,latitude,longitude,rainfall_mm,area_id
2024-07-01T00:00:00Z,22.7176,75.8506,2.3,IND
2024-07-01T01:00:00Z,22.7176,75.8506,5.1,IND
2024-07-01T02:00:00Z,22.7176,75.8506,0.8,IND
2024-07-01T00:00:00Z,23.1765,75.7885,3.7,UJJ
2024-07-01T01:00:00Z,23.1765,75.7885,1.2,UJJ
```

**Timestamp format:** ISO 8601 UTC (`YYYY-MM-DDTHH:MM:SSZ`). The adapter
also accepts `YYYY-MM-DD HH:MM:SS` and will convert to UTC.

**Units:** `rainfall_mm` must be mm/hour. If your source is mm/30min,
multiply by 2 before saving.

**Coordinates:** WGS84 decimal degrees. One row per grid cell per hour.
Aggregate to the nearest grid point for each area_id if needed.

### ERA5 sample (`era5.csv`)

```csv
timestamp,latitude,longitude,rainfall_mm,temperature_c,humidity,area_id
2024-07-01T00:00:00Z,22.7176,75.8506,2.3,32.5,78.0,IND
2024-07-01T01:00:00Z,22.7176,75.8506,5.1,31.8,82.0,IND
2024-07-01T02:00:00Z,22.7176,75.8506,0.8,30.2,85.0,IND
```

**Units:** `rainfall_mm` in mm/hour, `temperature_c` in Celsius,
`humidity` in percent (0-100). If your source uses metres for
precipitation, multiply by 1000. If Kelvin, subtract 273.15.
If humidity is a fraction (0-1), multiply by 100.

### CWC River Gauge sample (`cwc_river_data.csv`)

```csv
timestamp,gauge_id,river_name,stage_m,area_id,latitude,longitude
2024-07-01T00:00:00Z,NARM-IND-01,Narmada,3.2,IND,22.7176,75.8506
2024-07-01T01:00:00Z,NARM-IND-01,Narmada,3.5,IND,22.7176,75.8506
2024-07-01T02:00:00Z,NARM-IND-01,Narmada,4.1,IND,22.7176,75.8506
2024-07-01T00:00:00Z,SHIP-UJJ-01,Shipra,2.8,UJJ,23.1765,75.7885
2024-07-01T01:00:00Z,SHIP-UJJ-01,Shipra,3.1,UJJ,23.1765,75.7885
```

**Units:** `stage_m` in metres above local gauge datum.
**Critical:** `area_id` must match the area_id used in the GPM/ERA5
files so the merge aligns correctly. `gauge_id` must match the keys
in `flood_thresholds.json`.

### Optional: Gauge coordinates file (`gauge_coordinates.csv`)

If your CWC CSV does not include latitude/longitude, provide them
separately:

```csv
gauge_id,latitude,longitude
NARM-IND-01,22.7176,75.8506
SHIP-UJJ-01,23.1765,75.7885
```

## 6. Data Validation Example

Run this script to verify your data files are correctly formatted
before running the full pipeline:

```python
"""validate_data.py — quick check of real data files."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from backend.data.ingest.gpm_imerg import GPMIMERGAdapter
from backend.data.ingest.era5 import ERA5Adapter
from backend.data.ingest.cwc import CWCAdapter
from backend.forecasting.target import load_threshold_config

print("=== Validating GPM IMERG ===")
try:
    df = GPMIMERGAdapter().load()
    print(f"  OK: {len(df)} rows, {df['area_id'].nunique()} areas")
    print(f"  Time range: {df['timestamp'].min()} to {df['timestamp'].max()}")
    print(f"  Rainfall range: {df['rainfall_mm'].min():.1f} to {df['rainfall_mm'].max():.1f} mm/h")
except FileNotFoundError as e:
    print(f"  MISSING: {e}")
except Exception as e:
    print(f"  ERROR: {e}")

print("\n=== Validating ERA5 ===")
try:
    df = ERA5Adapter().load()
    print(f"  OK: {len(df)} rows, {df['area_id'].nunique()} areas")
    print(f"  Temp range: {df['temperature_c'].min():.1f} to {df['temperature_c'].max():.1f} C")
except FileNotFoundError as e:
    print(f"  MISSING: {e}")
except Exception as e:
    print(f"  ERROR: {e}")

print("\n=== Validating CWC River Gauges ===")
try:
    df = CWCAdapter().load()
    print(f"  OK: {len(df)} rows, {df['area_id'].nunique()} areas")
    print(f"  River level range: {df['river_level_m'].min():.1f} to {df['river_level_m'].max():.1f} m")
except FileNotFoundError as e:
    print(f"  MISSING: {e}")
except Exception as e:
    print(f"  ERROR: {e}")

print("\n=== Validating Flood Thresholds ===")
config = load_threshold_config()
if config.thresholds:
    print(f"  OK: {len(config.thresholds)} gauge thresholds defined")
    for g, t in config.thresholds.items():
        print(f"    {g}: {t} m")
else:
    print("  MISSING: No threshold config found. Create flood_thresholds.json")

print("\nDone. Fix any MISSING/ERROR items before running train_real.")
```

Save as `backend/data/real/validate_data.py` and run:
```bash
python backend/data/real/validate_data.py
```

## 7. Running the Pipeline

Once data is in place, run:

```bash
# 1. Ingest and validate data
python -m backend.forecasting.train_real

# This will:
# - Load data from all available adapters
# - Run data quality checks
# - Derive flood labels from river stage + thresholds
# - Build features
# - Train RandomForestClassifier
# - Evaluate on held-out test period
# - Save model to backend/forecasting/models/real_data_model.pkl
# - Save metadata to backend/forecasting/models/real_data_metadata.json
```

## Licensing and Usage

| Source | License | Restrictions |
|--------|---------|-------------|
| GPM IMERG | NASA Open Data | Free for research; cite NASA |
| ERA5 | Copernicus C3S | Free for non-commercial; cite ECMWF |
| CWC Data | Government of India | Free for research; cite CWC |

## What If Data Is Unavailable?

If you cannot obtain the required data:

1. **No CWC river gauge data:** You cannot define flood labels.
   Supervised real-world training CANNOT proceed. The synthetic
   model remains the only option.

2. **No GPM IMERG data:** You cannot build rainfall features.
   The model will have reduced predictive power.

3. **No documented flood thresholds:** You cannot define what
   constitutes a "flood event." Training cannot proceed.

In all cases, the system will clearly report what is missing
and will NOT silently substitute synthetic data.
