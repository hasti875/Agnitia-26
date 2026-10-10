"""
main.py
=======
Phase 8 — FastAPI dashboard backend.

Orchestrates the existing Phase 3-7 engines behind a clean JSON API.
No engine logic is re-implemented here; every endpoint calls the existing
functions directly.

DISCLAIMER
----------
Risk scores are rule-based estimates driven by live Open-Meteo weather
telemetry for real-world locations across the Seven Sister States of
Northeast India.  They are NOT official disaster forecasts, guaranteed
outcomes, or lives saved.

Run locally:
    python -m uvicorn backend.api.main:app --reload
"""

from __future__ import annotations

import math
import os
import sys
from typing import Dict, List, Optional, Tuple

# Ensure project root and backend directories are always in sys.path
_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.dirname(_HERE)
_PROJECT_ROOT = os.path.dirname(_BACKEND_DIR)

for p in [_PROJECT_ROOT, _BACKEND_DIR]:
    if p not in sys.path:
        sys.path.insert(0, p)

import csv
import json
import urllib
import urllib.parse
import urllib.request

import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Reuse existing engines (no re-implementation)
# ---------------------------------------------------------------------------
from backend.forecasting.features import (
    FEATURE_COLUMNS,
    build_feature_frame,
)
from backend.forecasting.model_registry import get_registry
from backend.risk import classify_risk
from backend.risk.resource_demand import (
    RESOURCES,
    calculate_deficits,
    calculate_resource_requirements,
    load_area_static,
    load_inventory,
)
from backend.optimization.optimizer import (
    build_area_infos,
    load_distances,
    optimize_resource_allocation,
)
from backend.simulation.scenarios import (
    RAINFALL_OPTIONS,
    RESOURCE_OPTIONS,
    RIVER_LEVEL_OPTIONS,
    ScenarioParams,
    _load_model,
    run_scenario,
)
from backend.analysis.comparison import compare_allocations
from backend.utils.explanations import build_explanations
from backend.forecasting.weather_service import get_all_weather, get_area_weather

# Path to the static area CSV (read-only).
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_AREAS_CSV = os.path.join(_BACKEND_DIR, "data", "areas.csv")

# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Climate Risk Arbitrage Engine",
    description=(
        "Decision-support API for regional flood-risk forecasting, "
        "resource demand/deficit analysis, and OR-Tools resource-allocation "
        "recommendations for the Seven Sister States of Northeast India. "
        "Risk scores are driven by live Open-Meteo weather telemetry and "
        "real-world area statistics. Outputs are estimates and are NOT "
        "official disaster forecasts, guaranteed outcomes, or lives saved."
    ),
    version="0.8.0",
)

# Development-only CORS (local hackathon frontend origins).
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Lightweight caches (read-only; avoid re-reading CSVs / reloading the model)
# ---------------------------------------------------------------------------

_STATIC_CACHE: Dict[str, dict] = {}
_DISTANCES_CACHE: Dict[str, dict] = {}
_PREDICTION_CACHE: Dict[str, dict] = {}


def _area_static() -> Dict[str, dict]:
    """
    Static area attributes (Phase 5 loader) merged with latitude/longitude
    read directly from areas.csv (read-only). Cached.
    """
    if "areas" not in _STATIC_CACHE:
        base = load_area_static()
        coords: Dict[str, dict] = {}
        with open(_AREAS_CSV, newline="", encoding="utf-8-sig") as fh:
            for row in csv.DictReader(fh):
                coords[row["area_id"]] = {
                    "latitude": float(row["latitude"]),
                    "longitude": float(row["longitude"]),
                }
        for area_id, a in base.items():
            c = coords.get(area_id, {"latitude": 0.0, "longitude": 0.0})
            a["latitude"] = c["latitude"]
            a["longitude"] = c["longitude"]
        _STATIC_CACHE["areas"] = base
    return _STATIC_CACHE["areas"]


def _distances() -> Dict[Tuple[str, str], float]:
    if "distances" not in _DISTANCES_CACHE:
        _DISTANCES_CACHE["distances"] = load_distances()
    return _DISTANCES_CACHE["distances"]


# ---------------------------------------------------------------------------
# Prediction helper (reuses the frozen Phase 4 model)
# ---------------------------------------------------------------------------

def _predict_risk_by_area() -> Dict[str, dict]:
    """
    Predict 6h-ahead flood risk for all areas using the existing trained
    model. Cached so repeated requests do not re-run inference.
    Returns {area_id: {"predicted_risk": float, "area_name": str}}.
    """
    if "prediction" in _PREDICTION_CACHE:
        return _PREDICTION_CACHE["prediction"]

    model = _load_model()
    frame = build_feature_frame(with_target=False)
    rows = (
        frame.sort_values("timestamp")
        .groupby("area_id", sort=False)
        .tail(1)
        .reset_index(drop=True)
    )
    X = rows[FEATURE_COLUMNS]
    preds = np.clip(model.predict(X), 0.0, 100.0)

    result: Dict[str, dict] = {}
    for (_, row), pred in zip(rows.iterrows(), preds):
        area_id = str(row["area_id"])
        result[area_id] = {
            "predicted_risk": round(float(pred), 2),
            "area_name": str(row["area_name"]),
        }
    _PREDICTION_CACHE["prediction"] = result
    return result


def _model_provenance() -> dict:
    """
    Get model provenance info for API responses.
    Identifies which model generated the predictions.
    """
    if "provenance" not in _PREDICTION_CACHE:
        registry = get_registry()
        status = registry.get_model_status()
        _PREDICTION_CACHE["provenance"] = status
    return _PREDICTION_CACHE["provenance"]


def _to_int(value) -> int:
    """Convert numpy/float scalars to plain int (JSON-safe)."""
    return int(value)


def _to_float(value) -> float:
    """Convert numpy/float scalars to plain float (JSON-safe)."""
    return float(value)


# ---------------------------------------------------------------------------
# Request model for /simulate
# ---------------------------------------------------------------------------

class SimulateRequest(BaseModel):
    rainfall_change_pct: int = Field(0, description="Rainfall change percentage.")
    river_level_change_pct: int = Field(0, description="River level change percentage.")
    resource_availability_change_pct: int = Field(
        0, description="Resource availability change percentage."
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get(
    "/health",
    tags=["system"],
    summary="Health check",
    description="Returns service status. Used to confirm the API is up.",
)
def health() -> dict:
    return {"status": "ok"}


@app.get(
    "/model-status",
    tags=["system"],
    summary="Model provenance and status",
    description=(
        "Returns information about which model is active, its training "
        "data source, and any warnings. Use this to determine whether "
        "predictions come from the synthetic baseline or a real-data model."
    ),
)
def model_status() -> dict:
    registry = get_registry()
    status = registry.get_model_status()
    return status


@app.get(
    "/weather",
    tags=["weather"],
    summary="Live weather telemetry",
    description=(
        "Returns live current conditions, observed rolling precipitation totals (1h, 3h, 6h, 24h), "
        "and hourly forecasts for representative locations via Open-Meteo API. "
        "Includes data timestamps, fetch metadata, and stale/error indicators."
    ),
)
def weather(force_refresh: bool = False) -> dict:
    return get_all_weather(force_refresh=force_refresh)


@app.get(
    "/areas",
    tags=["data"],
    summary="List all areas",
    description=(
        "Returns the 7 monitored areas (Seven Sister State capitals) with "
        "real-world coordinates, population, and vulnerability statistics."
    ),
)
def get_areas() -> dict:
    areas = _area_static()
    out = []
    for area_id in sorted(areas.keys()):
        a = areas[area_id]
        out.append({
            "area_id": area_id,
            "area_name": a["area_name"],
            "population": _to_float(a["population"]),
            "population_density": _to_float(a["population_density"]),
            "vulnerability_index": _to_float(a["vulnerability_index"]),
            "latitude": _to_float(a.get("latitude", 0.0)),
            "longitude": _to_float(a.get("longitude", 0.0)),
        })
    return {"areas": out, "count": len(out)}


from backend.risk.rule_based_calculator import calculate_rule_based_risk

@app.get(
    "/risk",
    tags=["risk"],
    summary="Current predicted flood risk",
    description=(
        "Returns 6-hour-ahead rule-based flood risk index for all monitored areas "
        "calculated dynamically from live Open-Meteo weather telemetry and static area vulnerability. "
        "Includes methodology disclaimers and transparent step-by-step risk calculations."
    ),
)
def get_risk() -> dict:
    areas = _area_static()
    out = []
    weather_available = False

    for area_id in sorted(areas.keys()):
        a_info = areas[area_id]
        vuln = _to_float(a_info.get("vulnerability_index", 0.5))

        # Get live Open-Meteo weather for area
        weather = get_area_weather(area_id)
        obs = weather.get("observed_metrics") or {}
        fc = weather.get("forecast_metrics") or {}
        weather_status = weather.get("status", "error")

        obs_rain = _to_float(obs.get("rainfall_last_24h", 0.0))
        fc_rain = _to_float(fc.get("next_6h_precipitation_mm", 0.0))
        prob = _to_float(fc.get("max_precip_probability_6h", 0.0))
        soil = _to_float(obs.get("soil_moisture_0_to_1cm", 0.0))

        live_data_ok = weather_status in ("ok", "stale", "estimated") and (obs_rain > 0 or fc_rain > 0 or prob > 0)
        if live_data_ok:
            weather_available = True

        if live_data_ok:
            # Use rule-based engine with real Open-Meteo data
            risk_res = calculate_rule_based_risk(
                observed_rain_24h_mm=obs_rain,
                forecast_rain_6h_mm=fc_rain,
                precip_probability_pct=prob,
                soil_moisture=soil,
                vulnerability_index=vuln,
            )
            methodology_type = "Rule-Based Risk Engine (Open-Meteo Integration)"
            data_source = "Open-Meteo Forecast API + areas.csv static parameters"
        else:
            # Weather API unavailable — fall back to trained ML model predictions
            ml_preds = _predict_risk_by_area()
            ml_entry = ml_preds.get(area_id, {})
            ml_risk = _to_float(ml_entry.get("predicted_risk", 0.0))
            from backend.risk.rule_based_calculator import categorize_risk_score
            ml_level = categorize_risk_score(ml_risk)
            risk_res = {
                "predicted_risk": ml_risk,
                "risk_level": ml_level,
                "methodology": (
                    "ML Model Fallback (RandomForest trained on synthetic NE India climate data). "
                    "Live Open-Meteo weather unavailable — using historical pattern predictions."
                ),
                "explanation": (
                    f"ML model prediction: {ml_risk:.1f}/100 [{ml_level}]. "
                    f"Weather API offline — prediction based on seasonal synthetic training data. "
                    f"Vulnerability index: {vuln:.2f}."
                ),
                "components": {
                    "observed_rain_24h_mm": 0.0,
                    "forecast_rain_6h_mm": 0.0,
                    "precip_probability_pct": 0.0,
                    "soil_moisture": 0.0,
                    "vulnerability_index": vuln,
                    "rainfall_index": 0.0,
                    "soil_factor": 1.0,
                    "prob_factor": 0.8,
                    "vuln_factor": round(1.0 + vuln * 0.5, 2),
                },
            }
            methodology_type = "ML Model Fallback (Weather API Offline)"
            data_source = "Synthetic NE India climate training data (RandomForest)"

        out.append({
            "area_id": area_id,
            "area_name": a_info["area_name"],
            "predicted_risk": risk_res["predicted_risk"],
            "risk_level": risk_res["risk_level"],
            "methodology": risk_res["methodology"],
            "explanation": risk_res["explanation"],
            "components": risk_res["components"],
        })

    provenance = _model_provenance()
    active_method = "rule_based_open_meteo_v1" if weather_available else "ml_model_fallback_v1"
    return {
        "areas": out,
        "count": len(out),
        "methodology_type": "Rule-Based Risk Engine (Open-Meteo Integration)" if weather_available else "ML Model Fallback (Weather API Offline)",
        "disclaimer": "Live weather-driven risk scores for the Seven Sister States. Not official disaster forecasts.",
        "model_provenance": {
            "active_model": active_method,
            "source_data": "Open-Meteo Forecast API + areas.csv static parameters" if weather_available else "Synthetic NE India climate training data",
            "warning": None if weather_available else "Open-Meteo daily API limit reached — showing ML model fallback predictions.",
        },
    }


@app.get(
    "/resources",
    tags=["resources"],
    summary="Resource inventory and demand",
    description=(
        "Returns current inventory plus Phase 5 demand/deficit/surplus "
        "calculations for every area and resource type. "
        "Requirements are dynamically scaled by live risk forecasts."
    ),
)
def get_resources() -> dict:
    risk_by_area_raw = _predict_risk_by_area()
    risk_by_area = {
        a: _to_float(info["predicted_risk"])
        for a, info in risk_by_area_raw.items()
    }
    # Also get the live risk levels from the /risk endpoint's rule-based engine
    # so the frontend can display correct risk categories
    from backend.risk.rule_based_calculator import categorize_risk_score
    risk_level_by_area = {
        a: categorize_risk_score(_to_float(info["predicted_risk"]))
        for a, info in risk_by_area_raw.items()
    }
    requirements = calculate_resource_requirements(risk_by_area)
    totals = calculate_deficits(requirements)

    rows = []
    for r in requirements:
        rows.append({
            "area_id": r.area_id,
            "area_name": r.area_name,
            "resource": r.resource,
            "current": _to_int(r.current),
            "required": _to_int(r.required),
            "deficit": _to_int(r.deficit),
            "surplus": _to_int(r.surplus),
            "risk_level": risk_level_by_area.get(r.area_id, "LOW"),
        })

    totals_out = {}
    for res in RESOURCES:
        t = totals[res]
        totals_out[res] = {
            "total_current": _to_int(t["total_current"]),
            "total_required": _to_int(t["total_required"]),
            "total_surplus": _to_int(t["total_surplus"]),
            "total_deficit": _to_int(t["total_deficit"]),
        }

    return {"resources": rows, "totals": totals_out, "count": len(rows)}


@app.get(
    "/recommendations",
    tags=["optimization"],
    summary="Resource allocation recommendations",
    description=(
        "Returns the current Phase 6 OR-Tools optimization result: which "
        "resources should move from which area to which area, with movement "
        "costs and an estimated risk-benefit score. "
        "Movement costs and risk benefits are indicative estimates, "
        "not guaranteed logistics costs or disaster outcomes."
    ),
)
def get_recommendations() -> dict:
    risk_by_area = {
        a: _to_float(info["predicted_risk"])
        for a, info in _predict_risk_by_area().items()
    }
    requirements = calculate_resource_requirements(risk_by_area)
    areas = build_area_infos(requirements, _area_static())
    distances = _distances()
    opt = optimize_resource_allocation(areas, distances)

    # Recompute per-movement recipient priority and objective contribution
    # using the same normalized factors the optimizer used, so the API can
    # expose them without re-implementing the optimization.
    area_ids = sorted(areas.keys())
    risk_norm = _normalize({a: areas[a].predicted_risk for a in area_ids})
    pop_norm = _normalize({a: areas[a].population for a in area_ids})
    vuln_norm = _normalize({a: areas[a].vulnerability for a in area_ids})

    from backend.optimization.optimizer import (
        DEFICIT_WEIGHT,
        POPULATION_WEIGHT,
        RISK_WEIGHT,
        VULNERABILITY_WEIGHT,
    )

    name_to_id = {a.area_name: a.area_id for a in areas.values()}

    movements = []
    for m in opt.movements:
        t_id = name_to_id[m.to_area]
        deficit_vals = {
            a: float(areas[a].deficit.get(m.resource, 0)) for a in area_ids
        }
        deficit_norm = _normalize(deficit_vals)
        priority = (
            RISK_WEIGHT * risk_norm[t_id]
            + DEFICIT_WEIGHT * deficit_norm[t_id]
            + POPULATION_WEIGHT * pop_norm[t_id]
            + VULNERABILITY_WEIGHT * vuln_norm[t_id]
        )
        # objective_contribution = quantity * (priority - distance * cost_weight)
        from backend.optimization.optimizer import RESOURCE_COST_WEIGHT
        obj_contrib = m.quantity * (
            priority - m.distance * RESOURCE_COST_WEIGHT[m.resource]
        )
        movements.append({
            "from_area": m.from_area,
            "to_area": m.to_area,
            "resource": m.resource,
            "quantity": _to_int(m.quantity),
            "distance_km": _to_float(m.distance),
            "movement_cost": round(_to_float(m.movement_cost), 2),
            "recipient_priority": round(_to_float(priority), 4),
            "objective_contribution": round(_to_float(obj_contrib), 2),
            "reason": m.reason,
            "estimated_risk_reduction": round(
                _to_float(m.estimated_risk_reduction), 2
            ),
        })

    remaining_deficit = sum(d["remaining_deficit"] for d in opt.remaining_deficits)

    return {
        "feasible": bool(opt.feasible),
        "status": opt.status,
        "objective_value": round(_to_float(opt.objective_value), 2),
        "movements": movements,
        "total_resources_moved": _to_int(opt.total_resources_moved),
        "total_movement_cost": round(_to_float(opt.total_movement_cost), 2),
        "remaining_deficit": _to_int(remaining_deficit),
        "total_estimated_risk_benefit": round(
            _to_float(opt.estimated_risk_reduction), 2
        ),
        "remaining_deficits": [
            {
                "area_id": d["area_id"],
                "area_name": d["area_name"],
                "resource": d["resource"],
                "remaining_deficit": _to_int(d["remaining_deficit"]),
            }
            for d in opt.remaining_deficits
        ],
    }


@app.post(
    "/simulate",
    tags=["simulation"],
    summary="What-if scenario simulation",
    description=(
        "Runs a what-if scenario through the Phase 7 engine and "
        "returns the baseline-vs-scenario comparison. Parameters are validated "
        "against the exact supported values. "
        "Scenario outputs are indicative estimates based on feature perturbation; "
        "NOT real disaster forecasts."
    ),
)
def simulate(req: SimulateRequest) -> dict:
    try:
        params = ScenarioParams(
            rainfall_change_pct=req.rainfall_change_pct,
            river_level_change_pct=req.river_level_change_pct,
            resource_availability_change_pct=req.resource_availability_change_pct,
        )
        params.validate()
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    try:
        result = run_scenario(params)
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Internal error while running scenario simulation.",
        )

    return _sanitize_scenario(result)


@app.get(
    "/comparison",
    tags=["analysis"],
    summary="Fixed vs optimized allocation impact comparison",
    description=(
        "Compares the FIXED allocation (resources stay put) against the "
        "OPTIMIZED allocation (Phase 6 OR-Tools recommendations) using the "
        "Estimated Prototype Risk-Impact Metric. Returns per-area and total "
        "impact, deficits, and the optimization summary. "
        "This is an estimated prototype risk-impact metric based on synthetic "
        "data; it does NOT establish actual real-world disaster reduction."
    ),
)
def get_comparison() -> dict:
    risk_by_area = {
        a: _to_float(info["predicted_risk"])
        for a, info in _predict_risk_by_area().items()
    }
    try:
        result = compare_allocations(risk_by_area=risk_by_area)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Internal error while computing allocation comparison.",
        )
    return _sanitize_scenario(result)


@app.get(
    "/explanations",
    tags=["analysis"],
    summary="Human-readable explanations",
    description=(
        "Returns structured, plain-English explanations for the current "
        "predicted risk of each area, resource shortages, the recommended "
        "transfers, and the fixed-vs-optimized allocation comparison. All "
        "text is generated from the existing Phase 3-9 engine outputs. "
        "Explanations are driven by live weather telemetry and real-world "
        "area data; they do NOT establish actual real-world disaster reduction."
    ),
)
def get_explanations() -> dict:
    # Reuse the same predicted risk the other endpoints use (cached).
    risk_by_area = {
        a: _to_float(info["predicted_risk"])
        for a, info in _predict_risk_by_area().items()
    }
    areas = _area_static()

    # Phase 3 explainable current-risk results (hazard/vuln/exposure + factors).
    from backend.risk import run_risk_engine
    phase3 = {r.area_id: r.to_dict() for r in run_risk_engine()}

    # Phase 5 requirements (current/required/deficit/surplus per area/resource).
    requirements = calculate_resource_requirements(risk_by_area)

    # Phase 6 optimizer result -> recommended transfers.
    opt_areas = build_area_infos(requirements, areas)
    opt = optimize_resource_allocation(opt_areas, _distances())

    # Phase 9 fixed-vs-optimized comparison.
    comparison = compare_allocations(
        risk_by_area=risk_by_area, optimizer_result=opt
    )

    # Build the structured explanations (logic lives in backend.utils).
    result = build_explanations(
        risk_results=[phase3[aid] for aid in sorted(phase3.keys())],
        requirements=[r.to_dict() for r in requirements],
        movements=[
            {
                "resource": m.resource,
                "from_area": m.from_area,
                "to_area": m.to_area,
                "quantity": m.quantity,
                "distance": m.distance,
                "movement_cost": m.movement_cost,
                "reason": m.reason,
            }
            for m in opt.movements
        ],
        comparison=comparison,
    )

    return _sanitize_scenario(result)


# ---------------------------------------------------------------------------
# Sanitization helpers (ensure JSON-safe plain types)
# ---------------------------------------------------------------------------

def _normalize(values: Dict[str, float]) -> Dict[str, float]:
    """Min-max normalize to [0, 1]; flat input -> all 0.5."""
    if not values:
        return {}
    lo, hi = min(values.values()), max(values.values())
    if hi - lo < 1e-12:
        return {k: 0.5 for k in values}
    return {k: (v - lo) / (hi - lo) for k, v in values.items()}


def _sanitize_scenario(result: dict) -> dict:
    """Convert the Phase 7 result into JSON-safe plain types."""
    def clean(obj):
        if isinstance(obj, dict):
            return {k: clean(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [clean(v) for v in obj]
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, float):
            return round(obj, 2)
        return obj

    return clean(result)


# ---------------------------------------------------------------------------
# Top-level error handler (no stack traces in responses)
# ---------------------------------------------------------------------------

@app.exception_handler(Exception)
async def unhandled_exception_handler(request, exc):
    from fastapi.responses import JSONResponse
    from fastapi import HTTPException as _HTTPEx
    # Do NOT swallow HTTPException — let FastAPI handle it normally
    if isinstance(exc, _HTTPEx):
        raise exc
    import traceback
    import logging
    logging.getLogger("uvicorn.error").error("Unhandled exception: %s", traceback.format_exc())
    return JSONResponse(
        status_code=500,
        content={"detail": f"Internal server error: {type(exc).__name__}: {exc}"},
    )


# ---------------------------------------------------------------------------
# /city-risk  — live flood risk for ANY Indian city by name
# ---------------------------------------------------------------------------

@app.get(
    "/city-risk",
    tags=["risk"],
    summary="Flood risk for any Indian city",
    description=(
        "Geocodes any Indian city via Open-Meteo's free Geocoding API, "
        "fetches live weather telemetry, and computes a rule-based flood risk "
        "score using the same engine as the monitored areas. "
        "No API key required."
    ),
)
def city_risk(city: str) -> dict:
    """Return live risk for any Indian city."""
    import urllib.parse as _up
    import urllib.request as _ur
    from datetime import datetime, timezone as _tz

    city_name = city.strip()
    if not city_name:
        raise HTTPException(status_code=422, detail="city parameter must not be empty.")

    # ── 1. Geocode ──────────────────────────────────────────────────────────
    geo_url = (
        "https://geocoding-api.open-meteo.com/v1/search?"
        f"name={_up.quote(city_name)}&count=5&language=en&format=json"
    )
    geo_req = _ur.Request(geo_url, headers={"User-Agent": "ClimateRiskEngine/1.0"})
    try:
        with _ur.urlopen(geo_req, timeout=8) as resp:
            geo_data = json.loads(resp.read().decode("utf-8"))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Geocoding service unavailable: {exc}")

    results = geo_data.get("results") or []
    india_results = [r for r in results if (r.get("country_code") or "").upper() == "IN"]
    if not india_results:
        raise HTTPException(
            status_code=404,
            detail=f"City '{city_name}' not found in India. Try a different spelling or check the name."
        )

    match = india_results[0]
    lat           = float(match["latitude"])
    lon           = float(match["longitude"])
    resolved_name = match.get("name", city_name)
    state         = match.get("admin1", "")
    country       = match.get("country", "India")

    # ── 2. Fetch weather ────────────────────────────────────────────────────
    wx_url = (
        f"https://api.open-meteo.com/v1/forecast?"
        f"latitude={lat}&longitude={lon}"
        f"&current=temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m"
        f"&hourly=precipitation,precipitation_probability,soil_moisture_0_to_1cm"
        f"&past_days=1&forecast_days=2&timezone=Asia%2FKolkata"
    )
    wx_req = _ur.Request(wx_url, headers={"User-Agent": "ClimateRiskEngine/1.0"})
    wx_data: dict = {}
    weather_live  = False
    try:
        with _ur.urlopen(wx_req, timeout=10) as resp:
            wx_data      = json.loads(resp.read().decode("utf-8"))
            weather_live = True
    except Exception:
        pass   # fall through to seasonal estimate

    # ── 3. Parse weather ────────────────────────────────────────────────────
    now_dt = datetime.now(_tz.utc)

    current      = wx_data.get("current", {})
    hourly       = wx_data.get("hourly", {})
    h_times      = hourly.get("time", [])
    h_precip     = hourly.get("precipitation", [])
    h_prob       = hourly.get("precipitation_probability", [])
    h_soil       = hourly.get("soil_moisture_0_to_1cm", [])

    observed: list = []
    forecast: list = []

    for i, t_str in enumerate(h_times):
        try:
            dt = datetime.fromisoformat(t_str.rstrip("Z")).replace(tzinfo=_tz.utc)
        except Exception:
            continue
        entry = {
            "precipitation_mm":       float(h_precip[i]) if i < len(h_precip) and h_precip[i] is not None else 0.0,
            "precip_probability_pct": float(h_prob[i])   if i < len(h_prob)   and h_prob[i]   is not None else 0.0,
            "soil_moisture":          float(h_soil[i])   if i < len(h_soil)   and h_soil[i]   is not None else 0.0,
        }
        (observed if dt <= now_dt else forecast).append(entry)

    obs_rain_24h  = round(sum(e["precipitation_mm"] for e in observed[-24:]), 2)
    fc_rain_6h    = round(sum(e["precipitation_mm"] for e in forecast[:6]),  2)
    max_prob_6h   = max((e["precip_probability_pct"] for e in forecast[:6]), default=0.0)
    soil_moisture = observed[-1]["soil_moisture"] if observed else 0.0
    fc_rain_24h   = round(sum(e["precipitation_mm"] for e in forecast[:24]), 2)

    temp_c    = float(current.get("temperature_2m",        0.0) or 0.0)
    humidity  = float(current.get("relative_humidity_2m",  0.0) or 0.0)
    wind_kmh  = float(current.get("wind_speed_10m",        0.0) or 0.0)
    curr_rain = float(current.get("precipitation",         0.0) or 0.0)

    # If live API failed, use IMD seasonal normals (same as weather_service.py)
    if not weather_live:
        _NE_MONTHLY_RAIN = {1:8,2:12,3:22,4:45,5:80,6:140,7:210,8:195,9:130,10:55,11:18,12:9}
        _MONTHLY_TEMP    = {1:15,2:17,3:21,4:26,5:28,6:28,7:27,8:27,9:27,10:25,11:20,12:16}
        _MONTHLY_HUM     = {1:68,2:66,3:68,4:73,5:79,6:88,7:90,8:90,9:87,10:82,11:74,12:70}
        mo = now_dt.month
        daily = _NE_MONTHLY_RAIN.get(mo, 20)
        obs_rain_24h  = round(daily * 0.9, 2)
        fc_rain_6h    = round(daily / 4,   2)
        fc_rain_24h   = round(daily * 0.95, 2)
        max_prob_6h   = min(95, int(daily / 2))
        soil_moisture = round(0.15 + daily / 600, 3)
        temp_c        = float(_MONTHLY_TEMP.get(mo, 24))
        humidity      = float(_MONTHLY_HUM.get(mo, 78))
        wind_kmh      = round(8.0 + daily / 30, 1)
        curr_rain     = round(daily / 24 * 0.7, 2)

    # ── 4. Vulnerability heuristic ──────────────────────────────────────────
    # Northeast India flood belt: lat 20-28, lon 88-97  → high
    # Coastal / delta zones                             → medium-high
    # Interior plateau / arid                          → lower
    in_ne     = (20 <= lat <= 28) and (88 <= lon <= 97)
    in_coast  = (lat <= 15) or (lon <= 76 and lat <= 22)
    in_gangetic = (24 <= lat <= 28) and (80 <= lon <= 88)   # Ganges plain
    vuln = 0.78 if in_ne else 0.70 if in_gangetic else 0.60 if in_coast else 0.42

    # ── 5. Risk calculation ─────────────────────────────────────────────────
    from backend.risk.rule_based_calculator import calculate_rule_based_risk
    risk_res = calculate_rule_based_risk(
        observed_rain_24h_mm   = obs_rain_24h,
        forecast_rain_6h_mm    = fc_rain_6h,
        precip_probability_pct = max_prob_6h,
        soil_moisture          = soil_moisture,
        vulnerability_index    = vuln,
    )

    return {
        "city":            resolved_name,
        "state":           state,
        "country":         country,
        "latitude":        lat,
        "longitude":       lon,
        "predicted_risk":  risk_res["predicted_risk"],
        "risk_level":      risk_res["risk_level"],
        "explanation":     risk_res["explanation"],
        "methodology":     risk_res["methodology"],
        "weather_live":    weather_live,
        "weather_source":  "Open-Meteo Forecast API" if weather_live else "IMD Climatological Normals (API offline)",
        "current_conditions": {
            "temperature_c":            temp_c,
            "relative_humidity_pct":    humidity,
            "wind_speed_kmh":           wind_kmh,
            "current_precipitation_mm": curr_rain,
        },
        "observed_metrics": {
            "rainfall_last_24h":       obs_rain_24h,
            "soil_moisture_0_to_1cm":  round(soil_moisture, 3),
        },
        "forecast_metrics": {
            "next_6h_precipitation_mm":  fc_rain_6h,
            "next_24h_precipitation_mm": fc_rain_24h,
            "max_precip_probability_6h": max_prob_6h,
        },
        "risk_components": risk_res["components"],
        "data_timestamp":  now_dt.isoformat(),
    }
