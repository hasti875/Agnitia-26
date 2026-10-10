"""
comparison.py
=============
Phase 9 — Fixed vs Optimized Impact Comparison Engine.

PURPOSE
-------
Estimate the difference between two resource allocations for the same
predicted-risk state:

    A. FIXED allocation   — resources stay at their current locations.
    B. OPTIMIZED allocation — resources are moved according to the existing
       Phase 6 OR-Tools optimizer recommendations.

For each allocation we compute an **Estimated Prototype Risk-Impact Metric**
per area and in total, then compare them.

METRIC
------
    impact(area) = normalized_risk(area)
                   x exposure_factor(area)
                   x shortage_factor(area)

    normalized_risk   = predicted_risk / 100            (0..1)
    exposure_factor   = 0.5 + 0.5 * (w_pop*pop_norm
                                     + w_dens*dens_norm)  (0.5..1.0)
    shortage_factor   = 1 + SHORTAGE_GAIN * total_deficit
                                              / max(total_required, 1)  (>=1)

Rationale:
  * normalized_risk  — higher flood risk means a given shortage is more
    consequential.
  * exposure_factor  — more / denser population means more people affected.
    Bounded to [0.5, 1.0] so an area with zero population still carries some
    exposure weight (never exactly zero).
  * shortage_factor  — scales with the fraction of required resources that
    are missing.  When there is NO deficit the factor is exactly 1.0 (the
    metric then reflects pure risk x exposure).  It grows above 1.0 as the
    deficit grows relative to the requirement, so a larger shortage raises
    the impact.  The denominator uses max(total_required, 1) to avoid
    division by zero.

The metric is a prototype decision-support estimate.  It is NOT a measure of
lives saved, guaranteed disaster prevention, or proven real-world reduction.

DISCLAIMER
----------
This is an estimated prototype risk-impact metric based on synthetic data.
It does not establish actual real-world disaster reduction.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Reuse existing engines (no re-implementation)
# ---------------------------------------------------------------------------
from backend.risk.resource_demand import (
    RESOURCES,
    calculate_deficits,
    calculate_resource_requirements,
    load_area_static,
    load_inventory,
)
from backend.optimization.optimizer import (
    AreaInfo,
    Movement,
    OptimizationResult,
    build_area_infos,
    load_distances,
    optimize_resource_allocation,
)

# ---------------------------------------------------------------------------
# Configurable metric weights / coefficients
# ---------------------------------------------------------------------------

# Exposure: blend of normalized population and population density.
EXPOSURE_POP_WEIGHT    = 0.5   # weight on population (thousands)
EXPOSURE_DENSITY_WEIGHT = 0.5  # weight on population density (per km2)
EXPOSURE_BASE          = 0.5   # floor so exposure_factor is never 0
EXPOSURE_GAIN          = 0.5   # gain so exposure_factor tops out at 1.0

# Shortage: how strongly the deficit-to-requirement ratio raises impact.
SHORTAGE_GAIN = 1.0            # impact multiplier at 100% shortage

# Normalization ceilings (same order of magnitude as the prototype data).
POP_NORM_MAX    = 3500.0       # thousands
DENSITY_NORM_MAX = 3000.0      # per km2

METRIC_NAME = "estimated_prototype_risk_impact"


# ---------------------------------------------------------------------------
# Internal per-area inventory view
# ---------------------------------------------------------------------------

@dataclass
class AreaInventory:
    """Current (or post-transfer) inventory + requirement for one area."""
    area_id:    str
    area_name:  str
    predicted_risk: float
    population: float
    population_density: float
    current:    Dict[str, int] = field(default_factory=dict)
    required:   Dict[str, int] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Metric core
# ---------------------------------------------------------------------------

def _clip01(x: float) -> float:
    return max(0.0, min(1.0, x))


def exposure_factor(population: float, population_density: float) -> float:
    """Bounded exposure factor in [EXPOSURE_BASE, EXPOSURE_BASE+EXPOSURE_GAIN]."""
    pop_norm  = _clip01(population / POP_NORM_MAX)
    dens_norm = _clip01(population_density / DENSITY_NORM_MAX)
    blend = (EXPOSURE_POP_WEIGHT * pop_norm
             + EXPOSURE_DENSITY_WEIGHT * dens_norm)
    return EXPOSURE_BASE + EXPOSURE_GAIN * blend


def shortage_factor(total_deficit: int, total_required: int) -> float:
    """
    >= 1.0.  Equals 1.0 when there is no deficit.
    Grows with the deficit-to-requirement ratio.
    """
    if total_deficit <= 0:
        return 1.0
    denom = max(total_required, 1)
    return 1.0 + SHORTAGE_GAIN * (total_deficit / denom)


def area_impact(
    predicted_risk: float,
    population: float,
    population_density: float,
    total_deficit: int,
    total_required: int,
) -> float:
    """Per-area Estimated Prototype Risk-Impact Metric (always >= 0)."""
    risk_norm = _clip01(predicted_risk / 100.0)
    expo = exposure_factor(population, population_density)
    short = shortage_factor(total_deficit, total_required)
    return max(0.0, risk_norm * expo * short)


def _area_totals(inv: AreaInventory) -> Tuple[int, int]:
    """(total_deficit, total_required) across all resources for one area."""
    total_deficit = 0
    total_required = 0
    for res in RESOURCES:
        cur = inv.current.get(res, 0)
        req = inv.required.get(res, 0)
        total_required += req
        total_deficit += max(0, req - cur)
    return total_deficit, total_required


# ---------------------------------------------------------------------------
# Apply optimizer movements to an in-memory inventory
# ---------------------------------------------------------------------------

def _apply_movements(
    inventories: Dict[str, AreaInventory],
    movements: List[Movement],
) -> Dict[str, AreaInventory]:
    """
    Return a NEW dict of AreaInventory with each movement applied.
    Raises ValueError if a movement cannot be applied safely.
    """
    # name -> id lookup
    name_to_id = {a.area_name: a.area_id for a in inventories.values()}

    # Work on a copy of the current dicts.
    new_inv: Dict[str, AreaInventory] = {
        aid: AreaInventory(
            area_id=a.area_id,
            area_name=a.area_name,
            predicted_risk=a.predicted_risk,
            population=a.population,
            population_density=a.population_density,
            current=dict(a.current),
            required=dict(a.required),
        )
        for aid, a in inventories.items()
    }

    for m in movements:
        if m.quantity <= 0:
            raise ValueError(f"Movement quantity must be positive: {m}")
        f_id = name_to_id.get(m.from_area)
        t_id = name_to_id.get(m.to_area)
        if f_id is None or t_id is None:
            raise ValueError(
                f"Unknown area in movement: {m.from_area} -> {m.to_area}"
            )
        if f_id == t_id:
            raise ValueError(f"Self-transfer not allowed: {m.from_area}")
        if m.resource not in RESOURCES:
            raise ValueError(f"Unknown resource in movement: {m.resource}")

        available = new_inv[f_id].current.get(m.resource, 0)
        if m.quantity > available:
            raise ValueError(
                f"Donor {m.from_area} cannot send {m.quantity} {m.resource}; "
                f"only has {available}"
            )

        new_inv[f_id].current[m.resource] = available - m.quantity
        new_inv[t_id].current[m.resource] = (
            new_inv[t_id].current.get(m.resource, 0) + m.quantity
        )

        # Safety: never negative
        if new_inv[f_id].current[m.resource] < 0:
            raise ValueError(
                f"Negative inventory after transfer: {m.from_area} "
                f"{m.resource}"
            )

    return new_inv


# ---------------------------------------------------------------------------
# Build inventories from Phase 5 (fixed baseline)
# ---------------------------------------------------------------------------

def _build_inventories(
    risk_by_area: Dict[str, float],
    area_static: Optional[Dict[str, dict]] = None,
    inventory: Optional[Dict[str, dict]] = None,
) -> Dict[str, AreaInventory]:
    static = area_static if area_static is not None else load_area_static()
    inv = inventory if inventory is not None else load_inventory()

    requirements = calculate_resource_requirements(
        risk_by_area, area_static=static, inventory=inv
    )

    inventories: Dict[str, AreaInventory] = {}
    for r in requirements:
        a = static[r.area_id]
        inventories[r.area_id] = AreaInventory(
            area_id=r.area_id,
            area_name=r.area_name,
            predicted_risk=float(r.predicted_risk),
            population=float(a["population"]),
            population_density=float(a["population_density"]),
            current={res: int(inv[r.area_id]["current"][res]) for res in RESOURCES},
            required={res: int(r.required) for res in RESOURCES},
        )
    return inventories


# ---------------------------------------------------------------------------
# Per-allocation evaluation
# ---------------------------------------------------------------------------

def _evaluate(inventories: Dict[str, AreaInventory]) -> dict:
    """Compute per-area + total impact and deficits for one allocation."""
    area_results = []
    total_impact = 0.0
    resource_totals: Dict[str, dict] = {
        res: {"fixed_deficit": 0, "optimized_deficit": 0,
              "total_current": 0, "total_required": 0}
        for res in RESOURCES
    }

    for aid in sorted(inventories.keys()):
        inv = inventories[aid]
        total_deficit, total_required = _area_totals(inv)
        impact = area_impact(
            inv.predicted_risk, inv.population, inv.population_density,
            total_deficit, total_required,
        )
        total_impact += impact

        per_resource = {}
        for res in RESOURCES:
            cur = inv.current.get(res, 0)
            req = inv.required.get(res, 0)
            deficit = max(0, req - cur)
            surplus = max(0, cur - req)
            per_resource[res] = {
                "current": cur,
                "required": req,
                "deficit": deficit,
                "surplus": surplus,
            }
            resource_totals[res]["total_current"] += cur
            resource_totals[res]["total_required"] += req
            resource_totals[res]["fixed_deficit"] += deficit

        area_results.append({
            "area_id": aid,
            "area_name": inv.area_name,
            "predicted_risk": round(inv.predicted_risk, 2),
            "impact": round(impact, 4),
            "total_deficit": total_deficit,
            "total_required": total_required,
            "per_resource": per_resource,
        })

    return {
        "total_impact": total_impact,
        "area_results": area_results,
        "resource_totals": resource_totals,
    }


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def compare_allocations(
    risk_by_area: Optional[Dict[str, float]] = None,
    optimizer_result: Optional[OptimizationResult] = None,
    area_static: Optional[Dict[str, dict]] = None,
    inventory: Optional[Dict[str, dict]] = None,
) -> dict:
    """
    Compare FIXED (current) vs OPTIMIZED (Phase 6 recommendations) allocation.

    Parameters
    ----------
    risk_by_area : {area_id: predicted risk 0-100}.  If None, the Phase 4
                   forecast is used (via Phase 5's get_risk_inputs).
    optimizer_result : an existing Phase 6 OptimizationResult.  If None, the
                   Phase 6 optimizer is run on the same demand state.
    area_static / inventory : optional overrides (for scenario reuse).

    Returns
    -------
    JSON-serializable dict (see module docstring for the metric definition).
    """
    # --- Risk input ---------------------------------------------------------
    if risk_by_area is None:
        from backend.risk.resource_demand import get_risk_inputs
        risk_by_area, _ = get_risk_inputs()
    risk_by_area = {k: float(v) for k, v in risk_by_area.items()}

    static = area_static if area_static is not None else load_area_static()
    inv = inventory if inventory is not None else load_inventory()

    # --- Fixed baseline inventories ----------------------------------------
    fixed_inv = _build_inventories(risk_by_area, static, inv)

    # --- Optimizer result ---------------------------------------------------
    if optimizer_result is None:
        requirements = calculate_resource_requirements(
            risk_by_area, area_static=static, inventory=inv
        )
        areas = build_area_infos(requirements, static)
        distances = load_distances()
        optimizer_result = optimize_resource_allocation(areas, distances)

    if not optimizer_result.feasible:
        raise ValueError(
            "Optimizer result is not feasible; cannot produce a valid "
            "fixed-vs-optimized comparison."
        )

    # --- Apply movements to an in-memory copy ------------------------------
    try:
        optimized_inv = _apply_movements(fixed_inv, optimizer_result.movements)
    except ValueError as e:
        raise ValueError(f"Could not safely apply optimizer movements: {e}")

    # --- Evaluate both allocations -----------------------------------------
    fixed_eval = _evaluate(fixed_inv)
    optimized_eval = _evaluate(optimized_inv)

    # --- Per-area merge -----------------------------------------------------
    opt_by_id = {a["area_id"]: a for a in optimized_eval["area_results"]}
    area_results = []
    for fa in fixed_eval["area_results"]:
        oa = opt_by_id[fa["area_id"]]
        area_results.append({
            "area_id": fa["area_id"],
            "area_name": fa["area_name"],
            "predicted_risk": fa["predicted_risk"],
            "fixed_risk_impact": fa["impact"],
            "optimized_risk_impact": oa["impact"],
            "fixed_total_deficit": fa["total_deficit"],
            "optimized_total_deficit": oa["total_deficit"],
            "impact_change": round(oa["impact"] - fa["impact"], 4),
            "fixed_per_resource": fa["per_resource"],
            "optimized_per_resource": oa["per_resource"],
        })

    # --- Resource totals (fixed + optimized deficits) ----------------------
    resource_totals = {}
    for res in RESOURCES:
        ft = fixed_eval["resource_totals"][res]
        # optimized deficit per resource
        opt_deficit = sum(
            opt_by_id[a["area_id"]]["per_resource"][res]["deficit"]
            for a in fixed_eval["area_results"]
        )
        resource_totals[res] = {
            "total_current": ft["total_current"],
            "total_required": ft["total_required"],
            "fixed_deficit": ft["fixed_deficit"],
            "optimized_deficit": opt_deficit,
        }

    # --- Headline numbers ---------------------------------------------------
    fixed_impact = fixed_eval["total_impact"]
    optimized_impact = optimized_eval["total_impact"]
    absolute_reduction = fixed_impact - optimized_impact
    if fixed_impact > 0:
        percentage_reduction = (absolute_reduction / fixed_impact) * 100.0
    else:
        percentage_reduction = 0.0  # safe: no division by zero

    # --- Optimization summary (reuse actual Phase 6 result) ----------------
    remaining_deficit_total = sum(
        d["remaining_deficit"] for d in optimizer_result.remaining_deficits
    )
    optimization_summary = {
        "feasible": bool(optimizer_result.feasible),
        "status": optimizer_result.status,
        "objective_value": round(optimizer_result.objective_value, 2),
        "total_resources_moved": int(optimizer_result.total_resources_moved),
        "total_movements": int(optimizer_result.total_movements),
        "total_movement_cost": round(optimizer_result.total_movement_cost, 2),
        "total_estimated_risk_benefit": round(
            optimizer_result.estimated_risk_reduction, 2
        ),
        "remaining_deficit_total": int(remaining_deficit_total),
        "remaining_deficits": [
            {
                "area_id": d["area_id"],
                "area_name": d["area_name"],
                "resource": d["resource"],
                "remaining_deficit": int(d["remaining_deficit"]),
            }
            for d in optimizer_result.remaining_deficits
        ],
        "movements": [
            {
                "resource": m.resource,
                "from_area": m.from_area,
                "to_area": m.to_area,
                "quantity": int(m.quantity),
                "distance_km": round(float(m.distance), 1),
                "movement_cost": round(float(m.movement_cost), 2),
            }
            for m in optimizer_result.movements
        ],
    }

    return {
        "metric_name": METRIC_NAME,
        "fixed_risk_impact": round(fixed_impact, 4),
        "optimized_risk_impact": round(optimized_impact, 4),
        "absolute_reduction": round(absolute_reduction, 4),
        "percentage_reduction": round(percentage_reduction, 2),
        "area_results": area_results,
        "resource_totals": resource_totals,
        "optimization_summary": optimization_summary,
        "assumptions": [
            "Predicted flood risk is held constant between the fixed and "
            "optimized allocations (same Phase 4 forecast).",
            "Requirements are identical for both allocations (Phase 5).",
            "Only the physical location of existing resources changes; no "
            "resources are created or destroyed.",
            "Exposure uses population and population density from areas.csv.",
            "Shortage factor = 1 + SHORTAGE_GAIN * (deficit / max(required,1)); "
            "equals 1.0 when there is no deficit.",
        ],
        "limitations": [
            "This is an estimated risk-impact metric based on live weather "
            "telemetry and real-world area statistics for NE India.",
            "It does NOT measure lives saved, guaranteed disaster prevention, "
            "or proven real-world disaster reduction.",
            "A negative reduction is possible and valid if the optimized "
            "allocation scores worse under the defined metric.",
            "Movement costs are prototype estimates, not real logistics costs.",
        ],
    }
