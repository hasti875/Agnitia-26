"""
test_weather_service.py
========================
Automated tests for Open-Meteo weather service module.
"""

import os
import sys
import unittest
from datetime import datetime, timezone

# Ensure both project root and backend folder are in Python path
_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.dirname(_HERE)
_PROJECT_ROOT = os.path.dirname(_BACKEND_DIR)

for p in [_PROJECT_ROOT, _BACKEND_DIR]:
    if p not in sys.path:
        sys.path.insert(0, p)

try:
    from backend.forecasting.weather_service import (
        parse_iso_datetime,
        process_open_meteo_data,
        get_all_weather,
        get_area_weather,
        load_target_locations,
    )
except ImportError:
    from forecasting.weather_service import (
        parse_iso_datetime,
        process_open_meteo_data,
        get_all_weather,
        get_area_weather,
        load_target_locations,
    )

class TestWeatherService(unittest.TestCase):

    def test_load_locations(self):
        locations = load_target_locations()
        self.assertGreaterEqual(len(locations), 7)
        for loc in locations:
            self.assertIn("area_id", loc)
            self.assertIn("latitude", loc)
            self.assertIn("longitude", loc)

    def test_parse_iso_datetime(self):
        dt1 = parse_iso_datetime("2026-10-09T14:00")
        self.assertIsNotNone(dt1)
        self.assertEqual(dt1.year, 2026)
        self.assertEqual(dt1.tzinfo, timezone.utc)

        dt2 = parse_iso_datetime("2026-10-09T14:00:00Z")
        self.assertIsNotNone(dt2)

        dt_invalid = parse_iso_datetime("invalid-date")
        self.assertIsNone(dt_invalid)

    def test_process_open_meteo_data_rolling_rain(self):
        sample_raw = {
            "current": {
                "time": "2026-10-09T05:00",
                "temperature_2m": 25.0,
                "relative_humidity_2m": 80.0,
                "precipitation": 2.0,
                "rain": 2.0,
                "wind_speed_10m": 10.0,
            },
            "hourly": {
                "time": [
                    "2026-10-09T00:00",
                    "2026-10-09T01:00",
                    "2026-10-09T02:00",
                    "2026-10-09T03:00",
                    "2026-10-09T04:00",
                    "2026-10-09T05:00",
                    "2026-10-09T06:00",
                    "2026-10-09T07:00",
                ],
                "precipitation": [0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 10.0, 15.0],
                "rain": [0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 10.0, 15.0],
                "precipitation_probability": [0, 10, 20, 30, 40, 50, 80, 90],
                "relative_humidity_2m": [70, 72, 75, 78, 80, 82, 85, 90],
                "soil_moisture_0_to_1cm": [0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5, 0.55],
                "temperature_2m": [22, 23, 23, 24, 24, 25, 26, 27],
            }
        }

        loc_info = {"area_id": "IND", "area_name": "Indore", "latitude": 22.72, "longitude": 75.86}
        processed = process_open_meteo_data(sample_raw, loc_info)

        self.assertEqual(processed["status"], "ok")
        self.assertFalse(processed["is_stale"])
        self.assertEqual(processed["source"], "Open-Meteo Forecast API")

        obs = processed["observed_metrics"]
        fc = processed["forecast_metrics"]

        # Current time = 05:00. Observed hours: 00:00, 01:00, 02:00, 03:00, 04:00, 05:00
        # Values: [0.0, 1.0, 2.0, 3.0, 4.0, 5.0]
        # Past 1h (at 05:00): 5.0
        # Past 3h (03:00, 04:00, 05:00): 3.0 + 4.0 + 5.0 = 12.0
        # Past 6h (all 6): 0 + 1 + 2 + 3 + 4 + 5 = 15.0
        self.assertEqual(obs["rainfall_last_1h"], 5.0)
        self.assertEqual(obs["rainfall_last_3h"], 12.0)
        self.assertEqual(obs["rainfall_last_6h"], 15.0)

        # Forecast hours (06:00, 07:00): [10.0, 15.0] -> Next 6h sum = 25.0
        self.assertEqual(fc["next_6h_precipitation_mm"], 25.0)
        self.assertEqual(fc["max_precip_probability_6h"], 90.0)

    def test_live_get_area_weather(self):
        res = get_area_weather("IND")
        self.assertEqual(res["source"], "Open-Meteo Forecast API")
        self.assertIn("status", res)
        self.assertEqual(res["area_id"], "IND")

if __name__ == "__main__":
    unittest.main()
