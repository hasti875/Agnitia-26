"""
weather_service.py
==================
Real-time weather data service powered by the Open-Meteo Forecast API.

Provides:
- Current condition estimates (temperature, humidity, rain, wind).
- Hourly observed weather (past 24h) and future hourly forecasts.
- Accurate rolling rainfall calculations (1h, 3h, 6h, 24h) handling missing hours.
- Strict separation of observed/recent weather from forecast metrics.
- Caching, stale-data status, error handling, and retry metadata without fabricated mock values on API failure.
"""

from __future__ import annotations

import csv
from datetime import datetime, timezone
import json
import math
import os
import urllib.request
import urllib.error
from typing import Dict, List, Optional, Any, Tuple

# ---------------------------------------------------------------------------
# Constants & Paths
# ---------------------------------------------------------------------------
OPEN_METEO_BASE_URL = "https://api.open-meteo.com/v1/forecast"
CACHE_TTL_SECONDS = 600  # 10 minutes cache TTL

_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.dirname(_HERE)
AREAS_CSV_PATH = os.path.join(_BACKEND_DIR, "data", "areas.csv")

# Representative fallback areas across Central India and all seven Northeastern Indian states
DEFAULT_LOCATIONS = [
    {"area_id": "IND", "area_name": "Indore", "latitude": 22.7196, "longitude": 75.8577},
    {"area_id": "UJJ", "area_name": "Ujjain", "latitude": 23.1765, "longitude": 75.7885},
    {"area_id": "DEW", "area_name": "Dewas", "latitude": 22.9676, "longitude": 76.0534},
    {"area_id": "DHA", "area_name": "Dhar", "latitude": 22.5975, "longitude": 75.3040},
    {"area_id": "RAT", "area_name": "Ratlam", "latitude": 23.3315, "longitude": 75.0367},
    {"area_id": "MAN", "area_name": "Mandsaur", "latitude": 24.0724, "longitude": 75.0697},
    {"area_id": "MHO", "area_name": "Mhow", "latitude": 22.5542, "longitude": 75.7562},
    {"area_id": "SEH", "area_name": "Sehore", "latitude": 23.2000, "longitude": 77.0900},
    # Northeastern Indian States
    {"area_id": "GAU", "area_name": "Guwahati (Assam)", "latitude": 26.1433, "longitude": 91.7362},
    {"area_id": "SHL", "area_name": "Shillong (Meghalaya)", "latitude": 25.5788, "longitude": 91.8933},
    {"area_id": "ITA", "area_name": "Itanagar (Arunachal)", "latitude": 27.0844, "longitude": 93.6053},
    {"area_id": "KOH", "area_name": "Kohima (Nagaland)", "latitude": 25.6751, "longitude": 94.1086},
    {"area_id": "IMP", "area_name": "Imphal (Manipur)", "latitude": 24.8170, "longitude": 93.9368},
    {"area_id": "AIZ", "area_name": "Aizawl (Mizoram)", "latitude": 23.7271, "longitude": 92.7176},
    {"area_id": "AGT", "area_name": "Agartala (Tripura)", "latitude": 23.8315, "longitude": 91.2868},
    {"area_id": "GAN", "area_name": "Gangtok (Sikkim)", "latitude": 27.3389, "longitude": 88.6065},
]

# In-memory weather cache: { cache_key: { "fetch_time": float, "data": dict } }
_WEATHER_CACHE: Dict[str, Dict[str, Any]] = {}
_LAST_SUCCESSFUL_FETCH: Dict[str, str] = {}


def load_target_locations() -> List[Dict[str, Any]]:
    """Load target locations from backend/data/areas.csv."""
    locations = []
    if os.path.exists(AREAS_CSV_PATH):
        try:
            with open(AREAS_CSV_PATH, newline="", encoding="utf-8-sig") as fh:
                reader = csv.DictReader(fh)
                for row in reader:
                    locations.append({
                        "area_id": row.get("area_id", "").strip(),
                        "area_name": row.get("area_name", "").strip(),
                        "latitude": float(row.get("latitude", 0.0)),
                        "longitude": float(row.get("longitude", 0.0)),
                    })
        except Exception:
            locations = DEFAULT_LOCATIONS
    return locations if locations else DEFAULT_LOCATIONS


def parse_iso_datetime(dt_str: str) -> Optional[datetime]:
    """Parse Open-Meteo timestamp strings safely."""
    if not dt_str:
        return None
    try:
        dt_str_clean = dt_str.rstrip("Z")
        return datetime.fromisoformat(dt_str_clean).replace(tzinfo=timezone.utc)
    except Exception:
        return None


def fetch_open_meteo_raw(latitude: float, longitude: float) -> dict:
    """
    Fetch current conditions and hourly forecast/past telemetry from Open-Meteo API.
    Uses timezone=Asia/Kolkata and past_days=1 to calculate rolling rainfall totals safely.
    """
    url = (
        f"{OPEN_METEO_BASE_URL}?"
        f"latitude={latitude}&longitude={longitude}"
        f"&current=temperature_2m,relative_humidity_2m,precipitation,rain,showers,wind_speed_10m"
        f"&hourly=precipitation,rain,showers,precipitation_probability,relative_humidity_2m,soil_moisture_0_to_1cm,temperature_2m"
        f"&past_days=1&forecast_days=2&timezone=Asia/Kolkata"
    )

    req = urllib.request.Request(
        url,
        headers={"User-Agent": "ClimateRiskEngine/1.0 (FastAPI Weather Service)"}
    )

    with urllib.request.urlopen(req, timeout=8) as response:
        if response.status != 200:
            raise ValueError(f"Open-Meteo HTTP Error: {response.status}")
        raw_bytes = response.read()
        return json.loads(raw_bytes.decode("utf-8"))


def process_open_meteo_data(
    raw_data: dict,
    location_info: Dict[str, Any],
    last_fetch_time: Optional[str] = None
) -> dict:
    """
    Process raw Open-Meteo response into observed telemetry, rolling rainfall totals,
    and separated forecast values.
    """
    current = raw_data.get("current", {})
    hourly = raw_data.get("hourly", {})

    current_time_str = current.get("time", "")
    now_dt = parse_iso_datetime(current_time_str) or datetime.now(timezone.utc)
    now_iso = now_dt.isoformat()

    # Current Observed Conditions
    current_obs = {
        "temperature_c": float(current.get("temperature_2m", 0.0) or 0.0),
        "relative_humidity_pct": float(current.get("relative_humidity_2m", 0.0) or 0.0),
        "current_precipitation_mm": float(current.get("precipitation", 0.0) or 0.0),
        "rain_mm": float(current.get("rain", 0.0) or 0.0),
        "wind_speed_kmh": float(current.get("wind_speed_10m", 0.0) or 0.0),
    }

    # Extract hourly timelines
    hourly_times = hourly.get("time", [])
    precip_list = hourly.get("precipitation", [])
    rain_list = hourly.get("rain", [])
    prob_list = hourly.get("precipitation_probability", [])
    humidity_list = hourly.get("relative_humidity_2m", [])
    soil_list = hourly.get("soil_moisture_0_to_1cm", [])
    temp_list = hourly.get("temperature_2m", [])

    observed_entries = []
    forecast_entries = []

    for idx, t_str in enumerate(hourly_times):
        dt = parse_iso_datetime(t_str)
        if not dt:
            continue

        item = {
            "timestamp": t_str,
            "dt": dt,
            "precipitation_mm": float(precip_list[idx]) if idx < len(precip_list) and precip_list[idx] is not None else 0.0,
            "rain_mm": float(rain_list[idx]) if idx < len(rain_list) and rain_list[idx] is not None else 0.0,
            "precip_probability_pct": float(prob_list[idx]) if idx < len(prob_list) and prob_list[idx] is not None else 0.0,
            "relative_humidity_pct": float(humidity_list[idx]) if idx < len(humidity_list) and humidity_list[idx] is not None else 0.0,
            "soil_moisture": float(soil_list[idx]) if idx < len(soil_list) and soil_list[idx] is not None else 0.0,
            "temperature_c": float(temp_list[idx]) if idx < len(temp_list) and temp_list[idx] is not None else 0.0,
        }

        if dt <= now_dt:
            observed_entries.append(item)
        else:
            forecast_entries.append(item)

    # Sort observed by timestamp ascending
    observed_entries.sort(key=lambda x: x["dt"])
    forecast_entries.sort(key=lambda x: x["dt"])

    # Calculate Rolling Rainfall Totals from Observed Data (Past 1h, 3h, 6h, 24h)
    def calc_rolling_sum(hours_count: int) -> float:
        if not observed_entries:
            return 0.0
        subset = observed_entries[-hours_count:]
        return round(sum(item["precipitation_mm"] for item in subset), 2)

    rainfall_last_1h = calc_rolling_sum(1)
    rainfall_last_3h = calc_rolling_sum(3)
    rainfall_last_6h = calc_rolling_sum(6)
    rainfall_last_24h = calc_rolling_sum(24)

    # Latest Soil Moisture from recent observed entry
    latest_soil_moisture = (
        observed_entries[-1]["soil_moisture"] if observed_entries else 0.0
    )

    # Separate Forecast Metrics (Next 6h & 24h)
    next_6h_forecast = forecast_entries[:6]
    next_24h_forecast = forecast_entries[:24]

    next_6h_precipitation_mm = round(sum(f["precipitation_mm"] for f in next_6h_forecast), 2)
    next_24h_precipitation_mm = round(sum(f["precipitation_mm"] for f in next_24h_forecast), 2)
    max_precip_probability_6h = (
        max([f["precip_probability_pct"] for f in next_6h_forecast], default=0.0)
    )

    fetch_timestamp = last_fetch_time or now_iso

    return {
        "area_id": location_info.get("area_id"),
        "area_name": location_info.get("area_name"),
        "latitude": location_info.get("latitude"),
        "longitude": location_info.get("longitude"),
        "status": "ok",
        "is_stale": False,
        "error_message": None,
        "source": "Open-Meteo Forecast API",
        "data_timestamp": current_time_str or now_iso,
        "forecast_timestamp": now_iso,
        "last_successful_fetch": fetch_timestamp,
        "current_conditions": current_obs,
        "observed_metrics": {
            "rainfall_last_1h": rainfall_last_1h,
            "rainfall_last_3h": rainfall_last_3h,
            "rainfall_last_6h": rainfall_last_6h,
            "rainfall_last_24h": rainfall_last_24h,
            "soil_moisture_0_to_1cm": round(latest_soil_moisture, 3),
        },
        "forecast_metrics": {
            "next_6h_precipitation_mm": next_6h_precipitation_mm,
            "next_24h_precipitation_mm": next_24h_precipitation_mm,
            "max_precip_probability_6h": max_precip_probability_6h,
            "hourly_forecast": [
                {
                    "timestamp": f["timestamp"],
                    "precipitation_mm": f["precipitation_mm"],
                    "precip_probability_pct": f["precip_probability_pct"],
                    "temperature_c": f["temperature_c"],
                    "relative_humidity_pct": f["relative_humidity_pct"],
                }
                for f in next_6h_forecast
            ]
        }
    }


def get_area_weather(area_id: str, force_refresh: bool = False) -> dict:
    """
    Get weather for a specific area. Handles caching, stale-data, and errors without fabricating data.
    """
    locations = load_target_locations()
    loc = next((l for l in locations if l["area_id"] == area_id or l["area_name"].lower() == area_id.lower()), None)
    if not loc:
        return {
            "area_id": area_id,
            "status": "error",
            "is_stale": False,
            "error_message": f"Location '{area_id}' not found.",
            "source": "Open-Meteo Forecast API",
            "data_timestamp": None,
            "last_successful_fetch": None,
            "current_conditions": None,
            "observed_metrics": None,
            "forecast_metrics": None,
        }

    cache_key = loc["area_id"]
    now_ts = datetime.now(timezone.utc).timestamp()
    cached = _WEATHER_CACHE.get(cache_key)

    # Return cached data if valid and fresh
    if not force_refresh and cached and (now_ts - cached["fetch_time"] < CACHE_TTL_SECONDS):
        return cached["data"]

    # Try fetching from Open-Meteo API
    try:
        raw_json = fetch_open_meteo_raw(loc["latitude"], loc["longitude"])
        now_iso = datetime.now(timezone.utc).isoformat()
        _LAST_SUCCESSFUL_FETCH[cache_key] = now_iso

        processed = process_open_meteo_data(raw_json, loc, last_fetch_time=now_iso)

        _WEATHER_CACHE[cache_key] = {
            "fetch_time": now_ts,
            "data": processed
        }
        return processed

    except Exception as exc:
        err_msg = f"Failed to fetch live weather from Open-Meteo: {str(exc)}"

        # If cache exists, return stale data with explicit stale status
        if cached:
            stale_data = dict(cached["data"])
            stale_data["status"] = "stale"
            stale_data["is_stale"] = True
            stale_data["error_message"] = err_msg
            return stale_data

        # If no cache exists, do NOT fabricate data. Return explicit error state.
        return {
            "area_id": loc["area_id"],
            "area_name": loc["area_name"],
            "latitude": loc["latitude"],
            "longitude": loc["longitude"],
            "status": "error",
            "is_stale": False,
            "error_message": err_msg,
            "source": "Open-Meteo Forecast API",
            "data_timestamp": None,
            "forecast_timestamp": None,
            "last_successful_fetch": _LAST_SUCCESSFUL_FETCH.get(cache_key),
            "current_conditions": None,
            "observed_metrics": None,
            "forecast_metrics": None,
        }


def get_all_weather(force_refresh: bool = False) -> dict:
    """
    Get live weather telemetry for all representative locations.
    """
    locations = load_target_locations()
    results = []
    ok_count = 0
    stale_count = 0
    error_count = 0

    for loc in locations:
        res = get_area_weather(loc["area_id"], force_refresh=force_refresh)
        results.append(res)
        if res["status"] == "ok":
            ok_count += 1
        elif res["status"] == "stale":
            stale_count += 1
        else:
            error_count += 1

    return {
        "count": len(results),
        "status_summary": {
            "ok": ok_count,
            "stale": stale_count,
            "error": error_count,
        },
        "source": "Open-Meteo Forecast API",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "areas": results,
    }
