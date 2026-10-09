"""
scenarios.py
============
Phase 7 — Deterministic What-If Scenario Engine.

PURPOSE
-------
Answer "what happens if …?" questions by perturbing the *inputs* of the
existing pipeline and re-running the SAME trained model and the SAME
Phase 5 / Phase 6 engines:

    rainfall multiplier      -> modifies rainfall features fed to the model
    river-level multiplier   -> modifies river features fed to the model
    resource availability    -> modifies the in-memory inventory

The Random Forest is loaded once and reused for the baseline and every
scenario.  It is NEVER retrained.  Source CSVs are never written to; all
perturbations happen on in-memory copies.

PHASE BOUNDARY
--------------
Backend scenario simulation only.  No FastAPI / React / map / Phase 8 / 9.

DISCLAIMER
----------
Scenario results are prototype what-if simulations based on synthetic data.
They are NOT real disaster forecasts.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Reuse existing modules (no re-implementation)
# ---------------------------------------------------------------------------
from backend.forecasting.features import (
    FEATURE_COLUMNS,
    MODEL_PATH,
    build_feature_frame,
    latest_feature_rows,
)
from backend.risk import classify_risk
from backend.risk.resource_demand import (
    RESOURCES,
    calculate_deficits,
    calculate_resource_requirements,
    load_area_static,
    load_inventory,
)
from backend.optimization.optimizer import (
    AreaInfo,
    OptimizationResult,
    build_area_infos,
    load_distances,
    optimize_resource_allocation,
)

# ---------------------------------------------------------------------------
# Supported scenario ranges (validated)
# ---------------------------------------------------------------------------

RAINFALL_OPTIONS    = [-30, -20, -10, 0, 10, 20, 30]
RIVER_LEVEL_OPTIONS = [-10, 0, 10, 20]
RESOURCE_OPTIONS    = [0, -10, -20, -30]

# ---------------------------------------------------------------------------
# Scenario parameters
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ScenarioParams:
    """Validated what-if scenario parameters (percentages)."""
    rainfall_change_pct: int = 0
    river_level_change_pct: int = 0
    resource_availability_change_pct: int = 0

    def validate(self) -> None:
        if self.rainfall_change_pct not in RAINFALL_OPTIONS:
            raise ValueError(
                f"rainfall_change_pct {self.rainfall_change_pct} not in "
                f"{RAINFALL_OPTIONS}"
            )
        if self.river_level_change_pct not in RIVER_LEVEL_OPTIONS:
            raise ValueError(
                f"river_level_change_pct {self.river_level_change_pct} not in "
                f"{RIVER_LEVEL_OPTIONS}"
            )
        if self.resource_availability_change_pct not in RESOURCE_OPTIONS:
            raise ValueError(
                f"resource_availability_change_pct "
                f"{self.resource_availability_change_pct} not in "
                f"{RESOURCE_OPTIONS}"
            )

    def is_baseline(self) -> bool:
        return (
            self.rainfall_change_pct == 0
            and self.river_level_change_pct == 0
            and self.resource_availability_change_pct == 0
        )

    def to_dict(self) -> dict:
        return {
            "rainfall_change_pct": self.rainfall_change_pct,
            "river_level_change_pct": self.river_level_change_pct,
            "resource_availability_change_pct":
                self.resource_availability_change_pct,
        }


# ---------------------------------------------------------------------------
# Model loading (shared, never retrained)
# ---------------------------------------------------------------------------

_MODEL_CACHE: Dict[str, object] = {}


def _load_model():
    """Load the frozen Random Forest once; reuse across baseline + scenarios."""
    if "model" not in _MODEL_CACHE:
        import joblib
        if not os.path.exists(MODEL_PATH):
            raise FileNotFoundError(
                "No trained model found. Train first:\n"
                "  python -m backend.forecasting.train"
            )
        _MODEL_CACHE["model"] = joblib.load(MODEL_PATH)
    return _MODEL_CACHE["model"]


# ---------------------------------------------------------------------------
# Scenario feature perturbation (in-memory)
# ---------------------------------------------------------------------------

def _perturb_features(
    frame: pd.DataFrame,
    params: ScenarioParams,
) -> pd.DataFrame:
    """
    Return an in-memory copy of the feature frame with rainfall and/or river
    features scaled by the scenario multipliers.

    Rainfall: every rainfall feature is multiplied by (1 + rainfall_pct/100).
              Because the rolling sums and trend are linear functions of the
              raw rainfall, scaling the raw column before feature construction
              is equivalent to scaling each derived feature consistently.
    River:    every river feature is multiplied by (1 + river_pct/100).

    The original `frame` is NOT modified.
    """
    out = frame.copy()

    rain_mult = 1.0 + params.rainfall_change_pct / 100.0
    river_mult = 1.0 + params.river_level_change_pct / 100.0

    rain_cols = [
        "rainfall_last_1h",
        "rainfall_last_3h",
        "rainfall_last_6h",
        "rainfall_trend",
    ]
    river_cols = [
        "river_level",
        "river_level_change",
        "river_level_trend",
    ]

    for c in rain_cols:
        if c in out.columns:
            out[c] = out[c] * rain_mult
    for c in river_cols:
        if c in out.columns:
            out[c] = out[c] * river_mult

    return out


def _predict_risk(
    feature_frame: pd.DataFrame,
    model,
) -> Dict[str, dict]:
    """
    Run the existing trained model on the (possibly perturbed) feature rows.

    Returns {area_id: {"predicted_risk": float, "area_name": str}}.
    """
    rows = (
        feature_frame.sort_values("timestamp")
        .groupby("area_id", sort=False)
        .tail(1)
        .reset_index(drop=True)
    )
    if rows.empty:
        raise ValueError("No feature rows available for prediction.")

    X = rows[FEATURE_COLUMNS]
    preds = np.clip(model.predict(X), 0.0, 100.0)

    result: Dict[str, dict] = {}
    for (_, row), pred in zip(rows.iterrows(), preds):
        area_id = str(row["area_id"])
        result[area_id] = {
            "predicted_risk": round(float(pred), 2),
            "area_name": str(row["area_name"]),
        }
    return result


# ---------------------------------------------------------------------------
# Resource availability perturbation (in-memory)
# ---------------------------------------------------------------------------

def _apply_resource_availability(
    inventory: Dict[str, dict],
    params: ScenarioParams,
) -> Dict[str, dict]:
    """
    Return an in-memory copy of the inventory with current quantities scaled
    by (1 + resource_pct/100), using floor rounding (documented rule).

    The original `inventory` is NOT modified.
    """
    mult = 1.0 + params.resource_availability_change_pct / 100.0
    out: Dict[str, dict] = {}
    for area_id, inv in inventory.items():
        out[area_id] = {
            "area_name": inv["area_name"],
            "current": {
                r: max(0, int(math.floor(inv["current"][r] * mult)))
                for r in RESOURCES
            },
            "static_baseline": dict(inv["static_baseline"]),
        }
    return out


# ---------------------------------------------------------------------------
# Full pipeline for one state (baseline or scenario)
# ---------------------------------------------------------------------------

def _run_pipeline(
    params: ScenarioParams,
    model,
    area_static: Dict[str, dict],
    distances: Dict[Tuple[str, str], float],
) -> dict:
    """
    Run the complete pipeline for a given set of scenario parameters and
    return a structured result dict.
    """
    # 1-4. Build feature frame (in-memory) and perturb
    feature_frame = build_feature_frame(with_target=False)
    perturbed = _perturb_features(feature_frame, params)

    # 5-6. Run the EXISTING trained model -> predicted risk
    risk_by_area = _predict_risk(perturbed, model)

    # 7. Phase 5 resource demand engine (needs {area_id: float})
    risk_floats = {
        a: risk_by_area.get(a, {}).get("predicted_risk", 0.0)
        for a in area_static
    }
    requirements = calculate_resource_requirements(
        risk_floats,
        area_static=area_static,
        inventory=_apply_resource_availability(
            load_inventory(), params
        ),
    )

    # 8. Deficits and surplus (Phase 5)
    totals = calculate_deficits(requirements)

    # 9. Phase 6 OR-Tools optimizer
    areas = build_area_infos(requirements, area_static)
    opt_result = optimize_resource_allocation(areas, distances)

    # Assemble structured result
    area_names = {a: area_static[a]["area_name"] for a in area_static}
    risk_info = []
    for area_id in sorted(area_static.keys()):
        pr = risk_by_area.get(area_id, {}).get("predicted_risk", 0.0)
        risk_info.append({
            "area_id": area_id,
            "area_name": area_names[area_id],
            "predicted_risk": pr,
            "risk_level": classify_risk(pr),
        })

    resource_info = []
    for r in requirements:
        resource_info.append({
            "area_id": r.area_id,
            "area_name": r.area_name,
            "resource": r.resource,
            "current": r.current,
            "required": r.required,
            "surplus": r.surplus,
            "deficit": r.deficit,
        })

    return {
        "risk": risk_info,
        "risk_by_area": {a["area_id"]: a["predicted_risk"] for a in risk_info},
        "resources": resource_info,
        "totals": totals,
        "optimizer": opt_result,
        "_risk_by_area_raw": {
            a: risk_by_area.get(a, {}).get("predicted_risk", 0.0)
            for a in area_static
        },
    }


# ---------------------------------------------------------------------------
# Comparison helpers
# ---------------------------------------------------------------------------

def _compare_risk(baseline: dict, scenario: dict) -> List[dict]:
    """Per-area risk change, sorted by largest positive increase first."""
    base_risk = baseline["risk_by_area"]
    scen_risk = scenario["risk_by_area"]
    base_level = {a["area_id"]: a["risk_level"] for a in baseline["risk"]}
    scen_level = {a["area_id"]: a["risk_level"] for a in scenario["risk"]}
    names = {a["area_id"]: a["area_name"] for a in baseline["risk"]}

    changes = []
    for area_id in sorted(base_risk.keys()):
        b = base_risk[area_id]
        s = scen_risk.get(area_id, b)
        changes.append({
            "area_id": area_id,
            "area_name": names[area_id],
            "baseline_predicted_risk": b,
            "scenario_predicted_risk": s,
            "risk_change": round(s - b, 2),
            "baseline_risk_level": base_level[area_id],
            "scenario_risk_level": scen_level[area_id],
        })
    changes.sort(key=lambda c: c["risk_change"], reverse=True)
    return changes


def _compare_resources(baseline: dict, scenario: dict) -> List[dict]:
    """Per area/resource change in current/required/surplus/deficit."""
    base_map = {
        (r["area_id"], r["resource"]): r for r in baseline["resources"]
    }
    scen_map = {
        (r["area_id"], r["resource"]): r for r in scenario["resources"]
    }
    out = []
    for key in sorted(base_map.keys()):
        b = base_map[key]
        s = scen_map.get(key, b)
        out.append({
            "area_id": key[0],
            "area_name": b["area_name"],
            "resource": key[1],
            "baseline_current": b["current"],
            "scenario_current": s["current"],
            "baseline_required": b["required"],
            "scenario_required": s["required"],
            "baseline_deficit": b["deficit"],
            "scenario_deficit": s["deficit"],
            "baseline_surplus": b["surplus"],
            "scenario_surplus": s["surplus"],
            "deficit_change": s["deficit"] - b["deficit"],
            "surplus_change": s["surplus"] - b["surplus"],
        })
    return out


def _compare_priorities(risk_changes: List[dict],
                        resource_changes: List[dict]) -> List[dict]:
    """
    Identify areas that became more or less urgent.
    An area is 'more urgent' if its risk increased OR any of its deficits
    increased.
    """
    risk_by_area = {c["area_id"]: c for c in risk_changes}
    deficit_by_area: Dict[str, List[dict]] = {}
    for rc in resource_changes:
        if rc["deficit_change"] != 0:
            deficit_by_area.setdefault(rc["area_id"], []).append(rc)

    priorities = []
    for area_id in sorted(risk_by_area.keys()):
        rc = risk_by_area[area_id]
        deficits = deficit_by_area.get(area_id, [])
        more_urgent = rc["risk_change"] > 0 or any(
            d["deficit_change"] > 0 for d in deficits
        )
        less_urgent = rc["risk_change"] < 0 and all(
            d["deficit_change"] <= 0 for d in deficits
        )
        if more_urgent or less_urgent:
            priorities.append({
                "area_id": area_id,
                "area_name": rc["area_name"],
                "baseline_predicted_risk": rc["baseline_predicted_risk"],
                "scenario_predicted_risk": rc["scenario_predicted_risk"],
                "risk_change": rc["risk_change"],
                "deficit_changes": [
                    {
                        "resource": d["resource"],
                        "baseline_deficit": d["baseline_deficit"],
                        "scenario_deficit": d["scenario_deficit"],
                        "change": d["deficit_change"],
                    }
                    for d in deficits
                ],
                "more_urgent": more_urgent,
                "less_urgent": less_urgent,
            })
    priorities.sort(
        key=lambda p: (not p["more_urgent"], -p["risk_change"]),
    )
    return priorities


def _compare_recommendations(
    baseline_opt: OptimizationResult,
    scenario_opt: OptimizationResult,
) -> dict:
    """
    Compare Phase 6 optimizer results: newly created, removed, and changed
    movements.
    """
    base_moves = {
        (m.resource, m.from_area, m.to_area): m.quantity
        for m in baseline_opt.movements
    }
    scen_moves = {
        (m.resource, m.from_area, m.to_area): m.quantity
        for m in scenario_opt.movements
    }

    added = []
    removed = []
    changed = []

    for key, q in sorted(scen_moves.items()):
        if key not in base_moves:
            added.append({
                "resource": key[0],
                "from_area": key[1],
                "to_area": key[2],
                "quantity": q,
            })
        elif base_moves[key] != q:
            changed.append({
                "resource": key[0],
                "from_area": key[1],
                "to_area": key[2],
                "baseline_quantity": base_moves[key],
                "scenario_quantity": q,
                "quantity_change": q - base_moves[key],
            })

    for key, q in sorted(base_moves.items()):
        if key not in scen_moves:
            removed.append({
                "resource": key[0],
                "from_area": key[1],
                "to_area": key[2],
                "quantity": q,
            })

    return {
        "added_movements": added,
        "removed_movements": removed,
        "changed_movements": changed,
        "baseline_total_movements": baseline_opt.total_movements,
        "scenario_total_movements": scenario_opt.total_movements,
    }


def _estimated_impact(
    baseline_opt: OptimizationResult,
    scenario_opt: OptimizationResult,
) -> dict:
    """Prototype impact comparison (labeled as estimates)."""
    return {
        "baseline_estimated_risk_benefit":
            baseline_opt.estimated_risk_reduction,
        "scenario_estimated_risk_benefit":
            scenario_opt.estimated_risk_reduction,
        "change_in_risk_benefit": round(
            scenario_opt.estimated_risk_reduction
            - baseline_opt.estimated_risk_reduction, 2
        ),
        "baseline_total_movement_cost":
            baseline_opt.total_movement_cost,
        "scenario_total_movement_cost":
            scenario_opt.total_movement_cost,
        "change_in_movement_cost": round(
            scenario_opt.total_movement_cost
            - baseline_opt.total_movement_cost, 2
        ),
        "baseline_total_resources_moved":
            baseline_opt.total_resources_moved,
        "scenario_total_resources_moved":
            scenario_opt.total_resources_moved,
        "note": (
            "Prototype estimates only. Not real disaster outcomes, "
            "lives saved, or financial savings."
        ),
    }


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_scenario(
    params: Optional[ScenarioParams] = None,
    as_of: Optional[str] = None,
) -> dict:
    """
    Run a what-if scenario and compare against the baseline.

    Parameters
    ----------
    params : ScenarioParams (validated). Defaults to baseline (all zeros).
    as_of  : Optional cutoff timestamp (passed through to feature builder).

    Returns
    -------
    Structured dict with baseline, scenario_result, and all comparisons.
    """
    if params is None:
        params = ScenarioParams()
    params.validate()

    model = _load_model()
    area_static = load_area_static()
    distances = load_distances()

    # Baseline (always computed from the unmodified system)
    baseline = _run_pipeline(ScenarioParams(), model, area_static, distances)

    # Scenario
    scenario = _run_pipeline(params, model, area_static, distances)

    risk_changes = _compare_risk(baseline, scenario)
    resource_changes = _compare_resources(baseline, scenario)
    priority_changes = _compare_priorities(risk_changes, resource_changes)
    recommendation_changes = _compare_recommendations(
        baseline["optimizer"], scenario["optimizer"]
    )
    impact = _estimated_impact(
        baseline["optimizer"], scenario["optimizer"]
    )

    return {
        "scenario": params.to_dict(),
        "baseline": _summarize(baseline),
        "scenario_result": _summarize(scenario),
        "risk_changes": risk_changes,
        "resource_changes": resource_changes,
        "priority_changes": priority_changes,
        "recommendation_changes": recommendation_changes,
        "estimated_impact": impact,
    }


def _summarize(pipeline_result: dict) -> dict:
    """Compact summary of a pipeline result for the output structure."""
    opt = pipeline_result["optimizer"]
    return {
        "risk_by_area": pipeline_result["risk_by_area"],
        "risk": pipeline_result["risk"],
        "resources": pipeline_result["resources"],
        "totals": pipeline_result["totals"],
        "optimizer": {
            "feasible": opt.feasible,
            "status": opt.status,
            "objective_value": opt.objective_value,
            "total_movement_cost": opt.total_movement_cost,
            "total_resources_moved": opt.total_resources_moved,
            "total_movements": opt.total_movements,
            "estimated_risk_reduction": opt.estimated_risk_reduction,
            "movements": [
                {
                    "resource": m.resource,
                    "from_area": m.from_area,
                    "to_area": m.to_area,
                    "quantity": m.quantity,
                    "distance": m.distance,
                    "movement_cost": m.movement_cost,
                    "reason": m.reason,
                    "estimated_risk_reduction": m.estimated_risk_reduction,
                }
                for m in opt.movements
            ],
            "remaining_deficits": opt.remaining_deficits,
        },
    }
