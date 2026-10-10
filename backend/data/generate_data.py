"""
generate_data.py
================
Synthetic historical climate data generator for the
Climate Risk Arbitrage Engine hackathon MVP.

IMPORTANT DISCLAIMER
--------------------
The climate_history.csv time series used to train the ML fallback model is
generated programmatically from IMD-calibrated monsoon parameters for NE India.
It is NOT official IMD or government data.  The regional names and coordinates
are real, but the numeric values are modelled estimates used to train a
monsoon-pattern-aware ML fallback for when the live weather API is unavailable.

Purpose
-------
Produce ~6 months of hourly records for the 7 Seven Sister States capitals of
Northeast India so that the ML forecasting, OR-Tools optimisation and React
dashboard can be developed and demonstrated without depending on any paid or
live data API.

Output files (all written to the same directory as this script)
---------------------------------------------------------------
  climate_history.csv   ~30,408 rows  (7 regions × ~175 days × 24 hours)
  areas.csv             7 rows        static region metadata
  resources.csv         7 rows        initial emergency resource inventory
  distances.csv         42 rows       approximate inter-region distances (prototype)

Usage
-----
  cd <project-root>
  python backend/data/generate_data.py
"""

import os
import math
import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Reproducibility
# ---------------------------------------------------------------------------
SEED = 42
rng = np.random.default_rng(SEED)

# ---------------------------------------------------------------------------
# Output directory — same folder as this script
# ---------------------------------------------------------------------------
OUT_DIR = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------------------
# Time range  (~6 months, hourly)
# ---------------------------------------------------------------------------
START_DATE = pd.Timestamp("2024-06-01 00:00:00")   # monsoon onset
END_DATE   = pd.Timestamp("2024-11-30 23:00:00")
FREQ       = "h"

timestamps = pd.date_range(start=START_DATE, end=END_DATE, freq=FREQ)
N_HOURS    = len(timestamps)           # ~4,344 hours per region

print(f"[INFO] Time range  : {START_DATE.date()} → {END_DATE.date()}")
print(f"[INFO] Hours/region: {N_HOURS}")

# ---------------------------------------------------------------------------
# Region definitions
# ---------------------------------------------------------------------------
# Each entry: area_id, area_name, base_rainfall_mm, river_level_base_m,
#             historical_flood_frequency (0–1), population (thousands),
#             population_density (per km²), vulnerability_index (0–1),
#             road_accessibility (0–1, higher = better roads)
REGION_META = [
    # id    name                             base_rain  rl_base  hff   pop   dens  vuln  road
    # Seven Sister States capitals — Northeast India
    # Guwahati: Brahmaputra basin, major flood-prone urban hub
    ("GAU", "Guwahati (Assam)",             9.5,       4.8,     0.82, 1100, 2900, 0.78, 0.72),
    # Shillong: Highland ridge, cloudburst flash-flood risk
    ("SHL", "Shillong (Meghalaya)",         8.2,       3.2,     0.68, 180,  1200, 0.68, 0.65),
    # Itanagar: Hilly terrain, moderate risk, better drainage
    ("ITA", "Itanagar (Arunachal Pradesh)", 6.0,       2.5,     0.55, 60,   400,  0.62, 0.55),
    # Kohima: Steep hill topography, landslide-flood interaction
    ("KOH", "Kohima (Nagaland)",            5.5,       2.2,     0.52, 120,  650,  0.58, 0.50),
    # Imphal: Valley basin with constrained drainage, high vulnerability
    ("IMP", "Imphal (Manipur)",             7.8,       3.8,     0.72, 270,  1600, 0.72, 0.60),
    # Aizawl: Ridge zone, lower flood history, good natural drainage
    ("AIZ", "Aizawl (Mizoram)",             5.8,       2.3,     0.48, 300,  950,  0.55, 0.58),
    # Agartala: River valley, Haora river flooding, high vulnerability
    ("AGT", "Agartala (Tripura)",           8.8,       4.2,     0.75, 520,  2100, 0.75, 0.68),
]

AREA_IDS   = [r[0] for r in REGION_META]
AREA_NAMES = [r[1] for r in REGION_META]

# ---------------------------------------------------------------------------
# Helper: seasonal envelope (monsoon peak in July–August)
# ---------------------------------------------------------------------------
def seasonal_envelope(timestamps):
    """
    Returns a value in [0, 1] representing the monsoon intensity at each hour.
    Peaks around day-of-year 210 (late July), fades by November.
    """
    doy = timestamps.day_of_year.values  # 0-indexed later via numpy
    # Gaussian-like shape centred on day 210, width ~45 days
    envelope = np.exp(-0.5 * ((doy - 210) / 45) ** 2)
    return envelope


# ---------------------------------------------------------------------------
# Helper: diurnal pattern (afternoon thunderstorms peak ~15:00)
# ---------------------------------------------------------------------------
def diurnal_pattern(timestamps):
    hour = timestamps.hour.values
    # Afternoon peak: cosine shifted so peak at hour 15
    return 0.5 + 0.5 * np.cos(2 * math.pi * (hour - 15) / 24 * -1)


# ---------------------------------------------------------------------------
# Generate climate series for ONE region
# ---------------------------------------------------------------------------
def generate_region_series(meta, timestamps, rng):
    area_id, area_name, base_rain, rl_base, hff, pop, dens, vuln, road = meta
    n = len(timestamps)

    season   = seasonal_envelope(timestamps)
    diurnal  = diurnal_pattern(timestamps)

    # ------------------------------------------------------------------
    # 1. Rainfall  (mm/hour)
    # ------------------------------------------------------------------
    # Base rate modulated by season + diurnal; Gamma-distributed drops
    # with occasional multi-hour heavy events injected.
    base_rate = base_rain * season * (0.6 + 0.4 * diurnal)

    # Gamma shape/scale gives right-skewed distribution typical of rainfall
    rain_raw = rng.gamma(shape=0.8, scale=base_rate + 0.1, size=n)

    # Inject ~8 heavy rain spells per season (each lasts 3–12 hours)
    heavy_events = rng.integers(0, n, size=8)
    for onset in heavy_events:
        duration = int(rng.integers(3, 13))
        intensity = rng.uniform(20, 60)   # mm/hr spike
        rain_raw[onset : onset + duration] += intensity * season[onset]

    # Temporal autocorrelation: wet hours tend to follow wet hours
    # Apply a simple exponential smoothing "persistence" pass
    rain_persist = np.zeros(n)
    alpha = 0.25   # persistence weight
    rain_persist[0] = rain_raw[0]
    for i in range(1, n):
        rain_persist[i] = alpha * rain_persist[i - 1] + (1 - alpha) * rain_raw[i]

    rainfall_mm = np.clip(rain_persist, 0, None)

    # ------------------------------------------------------------------
    # 2. River level  (metres) — responds to rainfall with lag
    # ------------------------------------------------------------------
    # River level rises as cumulative rainfall accumulates and drains slowly.
    # Lag: river reacts ~4–6 hours after rainfall.
    LAG_HOURS  = 5
    DRAIN_RATE = 0.985    # fraction remaining each hour (slow drain)

    river = np.zeros(n)
    river[0] = rl_base + rng.uniform(-0.1, 0.1)
    for i in range(1, n):
        rain_input = rainfall_mm[max(0, i - LAG_HOURS)]   # lagged rainfall
        # Rain-to-level conversion: heavier rain → bigger rise
        rise = rain_input * 0.018 * (1 + 0.3 * season[i])
        river[i] = river[i - 1] * DRAIN_RATE + rise
        # Mean-revert slowly toward base
        river[i] += 0.001 * (rl_base - river[i])

    river = np.clip(river, 0.3, 12.0)

    # ------------------------------------------------------------------
    # 3. Temperature  (°C) — seasonal + diurnal
    # ------------------------------------------------------------------
    # Hot pre-monsoon, cooler during heavy rain, mild in October–November
    temp_seasonal = 38 - 10 * season   # 28°C in peak monsoon, 38°C pre
    temp_diurnal  = 5 * np.cos(2 * math.pi * (timestamps.hour.values - 14) / 24)
    temp_noise    = rng.normal(0, 1.2, n)
    temperature_c = temp_seasonal + temp_diurnal + temp_noise

    # Rain cools temperature slightly
    temperature_c -= 0.08 * rainfall_mm
    temperature_c  = np.clip(temperature_c, 18, 46)

    # ------------------------------------------------------------------
    # 4. Humidity  (%)
    # ------------------------------------------------------------------
    # High in monsoon, lower otherwise; negatively correlated with temperature
    humidity_base  = 40 + 50 * season
    humidity_noise = rng.normal(0, 5, n)
    humidity       = humidity_base + 0.4 * rainfall_mm - 0.3 * (temperature_c - 30)
    humidity      += humidity_noise
    humidity       = np.clip(humidity, 20, 99)

    # ------------------------------------------------------------------
    # 5. Static regional attributes (broadcast to all rows)
    # ------------------------------------------------------------------
    hist_flood_freq   = np.full(n, hff)
    population        = np.full(n, pop)        # thousands
    pop_density       = np.full(n, dens)       # per km²
    vulnerability     = np.full(n, vuln)
    road_access       = np.full(n, road)

    # ------------------------------------------------------------------
    # 6. flood_risk target  (0–100)
    # ------------------------------------------------------------------
    # Synthetic ground-truth relationship — intentionally explainable:
    #
    #   flood_risk = f(hazard) × f(vulnerability) × f(exposure) + noise
    #
    # Hazard drivers (largest weight):
    #   H1 — recent 6-hour cumulative rainfall (rolling sum)
    #   H2 — river level above a danger threshold
    #   H3 — river level trend (rising or falling)
    #   H4 — historical flood frequency of the region
    #
    # Vulnerability / exposure drivers:
    #   V1 — vulnerability_index
    #   V2 — population density (normalised)
    #   V3 — road inaccessibility (1 - road_accessibility)

    # Rolling 6-hour cumulative rainfall (causal: only past values)
    cumrain_6h = pd.Series(rainfall_mm).rolling(6, min_periods=1).sum().values

    # River level trend: difference over last 3 hours
    river_series = pd.Series(river)
    river_trend  = river_series.diff(3).fillna(0).values   # positive = rising

    # Danger-level exceedance (normalised)
    DANGER_LEVEL = rl_base + 1.5
    river_exceed = np.clip((river - DANGER_LEVEL) / 3.0, 0, 1)

    # Hazard score (0–1)
    H1 = np.clip(cumrain_6h / 80, 0, 1)        # 80 mm in 6h = max hazard
    H2 = river_exceed
    H3 = np.clip(river_trend / 1.5, -1, 1) * 0.5 + 0.5   # 0–1, rising = 1
    H4 = hff                                    # scalar, 0–1

    hazard = 0.40 * H1 + 0.30 * H2 + 0.15 * H3 + 0.15 * H4

    # Vulnerability / exposure score (0–1)
    pop_norm = np.clip(dens / 3000, 0, 1)        # normalise by 3000/km²
    V1 = vuln
    V2 = pop_norm
    V3 = 1 - road                                # inaccessibility

    vul_exp = 0.50 * V1 + 0.30 * V2 + 0.20 * V3

    # Combined risk — multiplicative interaction between hazard and vulnerability
    risk_raw = hazard * (0.6 + 0.4 * vul_exp)

    # Scale to 0–100 and add realistic noise
    noise       = rng.normal(0, 3.5, n)
    flood_risk  = np.clip(risk_raw * 100 + noise, 0, 100)

    # ------------------------------------------------------------------
    # 7. flood_event  (binary)
    # ------------------------------------------------------------------
    # An event occurs when risk is high AND there is a rainfall spike.
    # Threshold varies slightly by region vulnerability.
    event_threshold = 65 - 10 * vuln   # more vulnerable regions need less to flood
    flood_event = ((flood_risk > event_threshold) &
                   (cumrain_6h > 25)).astype(int)

    # ------------------------------------------------------------------
    # Assemble DataFrame
    # ------------------------------------------------------------------
    df = pd.DataFrame({
        "timestamp":                timestamps,
        "area_id":                  area_id,
        "area_name":                area_name,
        "rainfall_mm":              np.round(rainfall_mm, 2),
        "river_level_m":            np.round(river, 3),
        "temperature_c":            np.round(temperature_c, 1),
        "humidity":                 np.round(humidity, 1),
        "historical_flood_frequency": np.round(hist_flood_freq, 2),
        "population":               population.astype(int),
        "population_density":       pop_density.astype(int),
        "vulnerability_index":      np.round(vulnerability, 2),
        "road_accessibility":       np.round(road_access, 2),
        "flood_event":              flood_event,
        "flood_risk":               np.round(flood_risk, 2),
    })

    return df


# ---------------------------------------------------------------------------
# Generate all regions
# ---------------------------------------------------------------------------
print("[INFO] Generating climate_history.csv ...")
frames = []
for meta in REGION_META:
    region_df = generate_region_series(meta, timestamps, rng)
    frames.append(region_df)
    print(f"       {meta[1]:<12} {len(region_df):>6,} rows  "
          f"flood events: {region_df['flood_event'].sum()}")

climate_df = pd.concat(frames, ignore_index=True)
climate_df.sort_values(["timestamp", "area_id"], inplace=True)
climate_df.reset_index(drop=True, inplace=True)

out_path = os.path.join(OUT_DIR, "climate_history.csv")
climate_df.to_csv(out_path, index=False)
print(f"[OK]   Saved: {out_path}  ({len(climate_df):,} rows)\n")


# ---------------------------------------------------------------------------
# areas.csv — static region metadata
# ---------------------------------------------------------------------------
print("[INFO] Generating areas.csv ...")
areas_data = {
    "area_id":                    [r[0] for r in REGION_META],
    "area_name":                  [r[1] for r in REGION_META],
    "latitude":  [26.1433, 25.5788, 27.0844, 25.6751, 24.8170, 23.7271, 23.8315],
    "longitude": [91.7362, 91.8933, 93.6053, 94.1086, 93.9368, 92.7176, 91.2868],
    "historical_flood_frequency": [r[4] for r in REGION_META],
    "population_thousands":       [r[5] for r in REGION_META],
    "population_density":         [r[6] for r in REGION_META],
    "vulnerability_index":        [r[7] for r in REGION_META],
    "road_accessibility":         [r[8] for r in REGION_META],
    "notes": [
        "Brahmaputra basin urban hub; highest flood risk in region",
        "Highland ridge; severe cloudburst and flash-flood risk",
        "Hilly terrain; moderate risk; slope drainage limits impact",
        "Steep hill topography; landslide-flood interaction risk",
        "Imphal valley basin; constrained drainage; high vulnerability",
        "Ridge zone; lower flood history; natural drainage advantage",
        "River valley; Haora river flooding; dense urban population",
    ],
}
areas_df = pd.DataFrame(areas_data)
areas_path = os.path.join(OUT_DIR, "areas.csv")
areas_df.to_csv(areas_path, index=False)
print(f"[OK]   Saved: {areas_path}  ({len(areas_df)} rows)\n")


# ---------------------------------------------------------------------------
# resources.csv — initial emergency resource allocation per region
# ---------------------------------------------------------------------------
# Allocation is intentionally uneven to create the deficit-detection scenario
# that the optimiser will later fix.
print("[INFO] Generating resources.csv ...")
resources_data = {
    "area_id":      ["GAU", "SHL", "ITA", "KOH", "IMP", "AIZ", "AGT"],
    "area_name":    [
        "Guwahati (Assam)", "Shillong (Meghalaya)", "Itanagar (Arunachal Pradesh)",
        "Kohima (Nagaland)", "Imphal (Manipur)", "Aizawl (Mizoram)", "Agartala (Tripura)"
    ],
    # Pumps — Itanagar and Aizawl have surplus; high-risk cities under-served
    "pumps":        [15,  9,  8,  6, 10,  9, 12],
    # Rescue teams — concentrated in larger cities
    "rescue_teams": [10,  6,  5,  4,  7,  6,  8],
    # Medical kits — broadly distributed but Guwahati/Agartala still short
    "medical_kits": [70, 35, 40, 25, 45, 45, 55],
    # Required capacity per city (used for deficit detection)
    "pumps_required":         [22, 14,  5, 11, 15,  6, 16],
    "rescue_teams_required":  [16,  9,  4,  7, 10,  4, 11],
    "medical_kits_required":  [95, 50, 25, 35, 60, 30, 70],
}
resources_df = pd.DataFrame(resources_data)
resources_path = os.path.join(OUT_DIR, "resources.csv")
resources_df.to_csv(resources_path, index=False)
print(f"[OK]   Saved: {resources_path}  ({len(resources_df)} rows)\n")


# ---------------------------------------------------------------------------
# distances.csv — prototype inter-region road distances (km)
# ---------------------------------------------------------------------------
# PROTOTYPE DISTANCES — These are approximate straight-line estimates with a
# 1.3× road-tortuosity factor applied.  They are NOT official route distances
# and must NOT be used for real logistics planning.
print("[INFO] Generating distances.csv ...")

# Symmetric distance matrix (km) — approximate road distances with ~1.3× tortuosity
# Order: GAU, SHL, ITA, KOH, IMP, AIZ, AGT
DIST_MATRIX = {
    #         GAU  SHL  ITA  KOH  IMP  AIZ  AGT
    "GAU": [   0, 102, 412, 345, 418, 510, 485],
    "SHL": [ 102,   0, 480, 330, 450, 440, 480],
    "ITA": [ 412, 480,   0, 320, 310, 560, 650],
    "KOH": [ 345, 330, 320,   0, 215, 420, 630],
    "IMP": [ 418, 450, 310, 215,   0, 380, 590],
    "AIZ": [ 510, 440, 560, 420, 380,   0, 440],
    "AGT": [ 485, 480, 650, 630, 590, 440,   0],
}

dist_rows = []
for src in AREA_IDS:
    for dst in AREA_IDS:
        if src != dst:
            dist_rows.append({
                "from_area_id":   src,
                "to_area_id":     dst,
                "distance_km":    DIST_MATRIX[src][AREA_IDS.index(dst)],
                "note":           "prototype estimate; not official routing distance",
            })

distances_df = pd.DataFrame(dist_rows)
distances_path = os.path.join(OUT_DIR, "distances.csv")
distances_df.to_csv(distances_path, index=False)
print(f"[OK]   Saved: {distances_path}  ({len(distances_df)} rows)\n")


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
print("=" * 60)
print("VALIDATION REPORT")
print("=" * 60)

df = climate_df.copy()

total_rows  = len(df)
n_regions   = df["area_id"].nunique()
date_range  = f"{df['timestamp'].min()}  →  {df['timestamp'].max()}"
n_floods    = int(df["flood_event"].sum())
avg_rain    = df["rainfall_mm"].mean()
avg_river   = df["river_level_m"].mean()
avg_risk    = df["flood_risk"].mean()
min_risk    = df["flood_risk"].min()
max_risk    = df["flood_risk"].max()

print(f"  Total rows           : {total_rows:,}")
print(f"  Regions              : {n_regions}")
print(f"  Date range           : {date_range}")
print(f"  Flood events         : {n_floods}")
print(f"  Avg rainfall (mm/hr) : {avg_rain:.3f}")
print(f"  Avg river level (m)  : {avg_river:.3f}")
print(f"  Avg flood risk       : {avg_risk:.2f}")
print(f"  Min / Max flood risk : {min_risk:.2f} / {max_risk:.2f}")
print()

errors = []

# No missing required values
required_cols = [
    "timestamp", "area_id", "area_name", "rainfall_mm", "river_level_m",
    "temperature_c", "humidity", "historical_flood_frequency",
    "population", "population_density", "vulnerability_index",
    "road_accessibility", "flood_event", "flood_risk",
]
for col in required_cols:
    missing = df[col].isna().sum()
    if missing > 0:
        errors.append(f"  FAIL: {col} has {missing} missing values")

# All 8 regions exist
for aid in AREA_IDS:
    if aid not in df["area_id"].values:
        errors.append(f"  FAIL: region {aid} not found")

# Timestamps ordered within each region
for aid in AREA_IDS:
    region_ts = df.loc[df["area_id"] == aid, "timestamp"]
    if not region_ts.is_monotonic_increasing:
        errors.append(f"  FAIL: timestamps not ordered for {aid}")

# flood_risk in [0, 100]
if df["flood_risk"].lt(0).any() or df["flood_risk"].gt(100).any():
    errors.append("  FAIL: flood_risk outside [0, 100]")

# No impossible negatives
for col in ["rainfall_mm", "river_level_m", "humidity", "population",
            "population_density"]:
    if df[col].lt(0).any():
        errors.append(f"  FAIL: {col} has negative values")

# flood_event is 0 or 1
invalid_events = ~df["flood_event"].isin([0, 1])
if invalid_events.any():
    errors.append("  FAIL: flood_event has values other than 0/1")

if errors:
    print("VALIDATION ERRORS:")
    for e in errors:
        print(e)
else:
    print("  All checks PASSED ✓")

print()
print("Per-region flood event counts:")
for aid, name in zip(AREA_IDS, AREA_NAMES):
    count = int(df.loc[df["area_id"] == aid, "flood_event"].sum())
    risk_mean = df.loc[df["area_id"] == aid, "flood_risk"].mean()
    print(f"  {aid} ({name:<10}): {count:>4} flood events  "
          f"avg risk = {risk_mean:.1f}")

print()
print("Done.  All CSV files written to:", OUT_DIR)
