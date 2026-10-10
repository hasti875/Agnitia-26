import sys
sys.path.insert(0, 'C:/Users/megha/Downloads/Agnitia-26-master')
from backend.forecasting.weather_service import build_seasonal_estimate, _climate_zone

cities = [
    ("Rajkot",    22.29, 70.79),
    ("Guwahati",  26.14, 91.74),
    ("Mumbai",    19.07, 72.88),
    ("Jaisalmer", 26.9,  70.9),
    ("Patna",     25.60, 85.12),
    ("Chennai",   13.08, 80.27),
]

for city, lat, lon in cities:
    zone = _climate_zone(lat, lon)
    e = build_seasonal_estimate({"latitude": lat, "longitude": lon, "area_id": city, "area_name": city})
    rain = e["observed_metrics"]["rainfall_last_24h"]
    temp = e["current_conditions"]["temperature_c"]
    src  = e["source"]
    print(f"{city:12s} zone={zone:12s} rain24h={rain:5.1f}mm  temp={temp}C")
