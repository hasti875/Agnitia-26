"""
optimizer.py
============
Phase 6 — Resource Allocation Optimization.

PURPOSE
-------
Given the Phase 5 resource-demand state (current vs required inventory per
area/resource) and the pairwise distance matrix, decide WHICH resources should
move FROM which area TO which area and HOW MUCH, using a linear integer
program solved by Google OR-Tools (CBC mixed-integer solver).

The optimizer does NOT create or destroy resources.  It only redistributes
genuine surplus to areas with a deficit, minimizing movement cost while
favoring recipients that combine high predicted flood risk, large deficits,
high population exposure and high vulnerability.

PHASE BOUNDARY
--------------
This module answers "what should move, from where, to where, and how much".
It does NOT implement:
  - FastAPI / React / map / scenario UI
  - Phase 8 fixed-vs-optimized impact comparison
  - Phase 9 natural-language explanation engine

DISCLAIMER
----------
This optimizer is a prototype decision-support model.  Movement costs and
risk benefits are estimated values for demonstration and are NOT real
emergency logistics costs or guaranteed disaster outcomes.
"""

from __future__ import annotations

import csv
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from ortools.linear_solver import pywraplp

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DATA_DIR    = os.path.join(_BACKEND_DIR, "data")
DISTANCES_CSV = os.path.join(_DATA_DIR, "distances.csv")

# ---------------------------------------------------------------------------
# Resource vocabulary (must match Phase 5)
# ---------------------------------------------------------------------------

RESOURCES: List[str] = ["pumps", "rescue_teams", "medical_kits"]

# ---------------------------------------------------------------------------
# Configurable objective weights
# ---------------------------------------------------------------------------
# Each weight scales one component of the per-unit benefit of delivering a
# unit of resource to a recipient area.  The objective is:
#
#   maximize  SUM_over_movements ( x[from,to,res] * benefit[to,res]
#                                  - x[from,to,res] * distance[from,to]
#                                  * RESOURCE_COST_WEIGHT[res] )
#
# where benefit[to,res] = RISK_WEIGHT * risk_norm[to]
#                        + DEFICIT_WEIGHT * deficit_norm[to,res]
#                        + POPULATION_WEIGHT * pop_norm[to]
#                        + VULNERABILITY_WEIGHT * vuln_norm[to]
#
# All *_norm terms are bounded in [0, 1] (see _normalize helpers), so the
# benefit of one unit lies in [0, RISK_WEIGHT+DEFICIT_WEIGHT
#                              +POPULATION_WEIGHT+VULNERABILITY_WEIGHT].
# The distance cost per unit is distance_km * RESOURCE_COST_WEIGHT[res],
# which for the prototype distances (25-210 km) and weights below is of
# comparable magnitude, so the solver genuinely trades off benefit vs cost.

RISK_WEIGHT         = 10.0   # high predicted flood risk -> higher benefit
DEFICIT_WEIGHT      = 12.0   # larger unmet need -> higher benefit (dominant)
POPULATION_WEIGHT   = 6.0    # more people exposed -> higher benefit
VULNERABILITY_WEIGHT = 6.0   # more fragile area -> higher benefit

# Movement cost per unit per km, by resource.  Pumps are heavy, rescue teams
# are people (expensive to re-deploy), medical kits are light.  These are
# prototype weights, not real logistics pricing.
RESOURCE_COST_WEIGHT: Dict[str, float] = {
    "pumps":        0.10,
    "rescue_teams": 0.15,
    "medical_kits": 0.05,
}

# ---------------------------------------------------------------------------
# Data records
# ---------------------------------------------------------------------------

@dataclass
class AreaInfo:
    """Static + dynamic attributes for one area (Phase 5 + areas.csv)."""
    area_id:            str
    area_name:          str
    predicted_risk:     float          # 0-100
    population:         float          # thousands
    population_density: float          # per km2
    vulnerability:      float          # 0-1
    current:            Dict[str, int] = field(default_factory=dict)
    required:           Dict[str, int] = field(default_factory=dict)
    surplus:            Dict[str, int] = field(default_factory=dict)
    deficit:            Dict[str, int] = field(default_factory=dict)


@dataclass
class Movement:
    """One recommended transfer of a resource between two areas."""
    resource:        str
    from_area:       str
    to_area:         str
    quantity:        int
    distance:        float
    movement_cost:   float
    reason:          str
    estimated_risk_reduction: float


@dataclass
class AreaFinalState:
    """Per-area per-resource state after the optimized movements."""
    area_id:            str
    area_name:          str
    resource:           str
    initial_quantity:   int
    inbound:            int
    outbound:           int
    final_quantity:     int
    required_quantity:  int
    remaining_deficit:  int
    remaining_surplus:  int


@dataclass
class OptimizationResult:
    """Full structured output of the optimizer (consumed by Phase 8/9)."""
    feasible:             bool
    status:               str
    objective_value:      float
    total_movement_cost:  float
    total_resources_moved: int
    total_movements:      int
    estimated_risk_reduction: float
    movements:            List[Movement]
    area_states:          List[AreaFinalState]
    remaining_deficits:   List[dict]
    baseline:             dict
    per_resource:         Dict[str, dict]


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

def load_distances(path: str = DISTANCES_CSV) -> Dict[Tuple[str, str], float]:
    """
    Read distances.csv into {(from_id, to_id): distance_km}.

    The file is symmetric (both directions present); we keep exactly what the
    file says so the optimizer only uses routes that exist in the dataset.
    """
    dist: Dict[Tuple[str, str], float] = {}
    with open(path, newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            dist[(row["from_area_id"], row["to_area_id"])] = float(
                row["distance_km"]
            )
    return dist


def build_area_infos(
    requirements: List,
    area_static:  Dict[str, dict],
) -> Dict[str, AreaInfo]:
    """
    Merge Phase 5 requirement records with static area attributes.

    Parameters
    ----------
    requirements : List[ResourceRequirement] from Phase 5
                   (backend.risk.resource_demand).
    area_static  : {area_id: {...}} from Phase 5 load_area_static().
    """
    areas: Dict[str, AreaInfo] = {}
    for r in requirements:
        a = area_static.get(r.area_id)
        if a is None:
            continue
        if r.area_id not in areas:
            areas[r.area_id] = AreaInfo(
                area_id            = r.area_id,
                area_name          = r.area_name,
                predicted_risk     = float(r.predicted_risk),
                population         = float(a["population"]),
                population_density = float(a["population_density"]),
                vulnerability      = float(a["vulnerability_index"]),
            )
        info = areas[r.area_id]
        info.current[r.resource]  = int(r.current)
        info.required[r.resource] = int(r.required)
        info.surplus[r.resource]  = int(r.surplus)
        info.deficit[r.resource]  = int(r.deficit)
    return areas


# ---------------------------------------------------------------------------
# Normalization helpers (all bounded to [0, 1])
# ---------------------------------------------------------------------------

def _normalize(values: Dict[str, float]) -> Dict[str, float]:
    """Min-max normalize a dict of values to [0, 1]; flat input -> all 0.5."""
    if not values:
        return {}
    lo, hi = min(values.values()), max(values.values())
    if hi - lo < 1e-12:
        return {k: 0.5 for k in values}
    return {k: (v - lo) / (hi - lo) for k, v in values.items()}


def _normalize_deficits(areas: Dict[str, AreaInfo], resource: str) -> Dict[str, float]:
    """Normalize deficits for one resource across areas (0 if no deficit)."""
    vals = {a: float(areas[a].deficit.get(resource, 0)) for a in areas}
    return _normalize(vals)


# ---------------------------------------------------------------------------
# Core optimization
# ---------------------------------------------------------------------------

def optimize_resource_allocation(
    areas:       Dict[str, AreaInfo],
    distances:   Dict[Tuple[str, str], float],
    risk_weight:      float = RISK_WEIGHT,
    deficit_weight:   float = DEFICIT_WEIGHT,
    population_weight: float = POPULATION_WEIGHT,
    vulnerability_weight: float = VULNERABILITY_WEIGHT,
    resource_cost_weights: Optional[Dict[str, float]] = None,
) -> OptimizationResult:
    """
    Solve the integer linear program that allocates surplus resources to
    deficit areas.

    Decision variables
    ------------------
    x[from, to, resource]  : integer >= 0
                             quantity of `resource` moved from `from` to `to`.
    A variable is created only for (from, to, resource) tuples where
      - from != to
      - (from, to) exists in distances.csv
      - areas[from].surplus[resource] > 0   (genuine donor)
      - areas[to].deficit[resource] > 0     (genuine recipient)

    Objective
    ---------
    maximize  SUM  x[f,t,res] * ( benefit[t,res]
                                  - distance[f,t] * cost_weight[res] )

    where benefit[t,res] = risk_w * risk_norm[t]
                          + deficit_w * deficit_norm[t,res]
                          + pop_w * pop_norm[t]
                          + vuln_w * vuln_norm[t]

    Constraints
    -----------
    For every donor d and resource r:
        SUM_t x[d,t,r] <= surplus[d,r]
    For every recipient t and resource r:
        SUM_f x[f,t,r] <= deficit[t,r]

    (Conservation, non-negativity, integrality, no self-moves and the
    donor/recipient eligibility rules are all enforced by construction of
    the variable set and these two constraint families.)
    """
    cost_w = resource_cost_weights or RESOURCE_COST_WEIGHT

    area_ids = sorted(areas.keys())

    # --- Normalized factors -------------------------------------------------
    risk_norm = _normalize({a: areas[a].predicted_risk for a in area_ids})
    pop_norm  = _normalize({a: areas[a].population for a in area_ids})
    vuln_norm = _normalize({a: areas[a].vulnerability for a in area_ids})
    deficit_norm: Dict[str, Dict[str, float]] = {
        res: _normalize_deficits(areas, res) for res in RESOURCES
    }

    # --- Per-recipient per-resource benefit ---------------------------------
    benefit: Dict[str, Dict[str, float]] = {}
    for res in RESOURCES:
        benefit[res] = {}
        for t in area_ids:
            benefit[res][t] = (
                risk_weight * risk_norm[t]
                + deficit_weight * deficit_norm[res][t]
                + population_weight * pop_norm[t]
                + vulnerability_weight * vuln_norm[t]
            )

    # --- Build candidate (from, to, resource) tuples ------------------------
    candidates: List[Tuple[str, str, str]] = []
    for f in area_ids:
        for t in area_ids:
            if f == t:
                continue
            if (f, t) not in distances:
                continue
            for res in RESOURCES:
                if areas[f].surplus.get(res, 0) > 0 and \
                   areas[t].deficit.get(res, 0) > 0:
                    candidates.append((f, t, res))

    # --- OR-Tools model ------------------------------------------------------
    solver = pywraplp.Solver(
        "resource_allocation",
        pywraplp.Solver.CBC_MIXED_INTEGER_PROGRAMMING,
    )
    solver.SuppressOutput()

    vars: Dict[Tuple[str, str, str], pywraplp.Variable] = {}
    for (f, t, res) in candidates:
        upper = min(areas[f].surplus[res], areas[t].deficit[res])
        if upper <= 0:
            continue
        v = solver.IntVar(0, upper, f"x_{f}_{t}_{res}")
        vars[(f, t, res)] = v

    # Objective: maximize benefit - cost
    objective_terms = []
    for (f, t, res), v in vars.items():
        per_unit = benefit[res][t] - distances[(f, t)] * cost_w[res]
        objective_terms.append(per_unit * v)
    if objective_terms:
        solver.Maximize(solver.Sum(objective_terms))
    else:
        solver.Maximize(0)

    # Donor constraints: outgoing <= surplus
    for f in area_ids:
        for res in RESOURCES:
            out = [v for (ff, tt, rr), v in vars.items()
                   if ff == f and rr == res]
            if out:
                solver.Add(solver.Sum(out) <= areas[f].surplus[res])

    # Recipient constraints: incoming <= deficit
    for t in area_ids:
        for res in RESOURCES:
            inc = [v for (ff, tt, rr), v in vars.items()
                   if tt == t and rr == res]
            if inc:
                solver.Add(solver.Sum(inc) <= areas[t].deficit[res])

    status = solver.Solve()

    # --- Baseline (no movement) ---------------------------------------------
    baseline = _build_baseline(areas)

    if status not in (solver.OPTIMAL, solver.FEASIBLE):
        return OptimizationResult(
            feasible=False,
            status="INFEASIBLE" if status == solver.INFEASIBLE else "SOLVE_ERROR",
            objective_value=0.0,
            total_movement_cost=0.0,
            total_resources_moved=0,
            total_movements=0,
            estimated_risk_reduction=0.0,
            movements=[],
            area_states=_final_states(areas, {}),
            remaining_deficits=_remaining_deficits(areas, {}),
            baseline=baseline,
            per_resource=_per_resource_summary(areas, {}, distances, cost_w),
        )

    # --- Extract solution ----------------------------------------------------
    solution: Dict[Tuple[str, str, str], int] = {}
    for key, v in vars.items():
        q = int(round(v.solution_value()))
        if q > 0:
            solution[key] = q

    movements = _build_movements(solution, areas, distances,
                                 cost_w, benefit)
    area_states = _final_states(areas, solution)
    remaining = _remaining_deficits(areas, solution)
    per_resource = _per_resource_summary(areas, solution, distances, cost_w)

    total_cost = sum(m.movement_cost for m in movements)
    total_moved = sum(m.quantity for m in movements)
    total_risk_reduction = sum(m.estimated_risk_reduction for m in movements)

    return OptimizationResult(
        feasible=True,
        status="OPTIMAL" if status == solver.OPTIMAL else "FEASIBLE",
        objective_value=float(solver.Objective().Value()),
        total_movement_cost=round(total_cost, 2),
        total_resources_moved=total_moved,
        total_movements=len(movements),
        estimated_risk_reduction=round(total_risk_reduction, 2),
        movements=movements,
        area_states=area_states,
        remaining_deficits=remaining,
        baseline=baseline,
        per_resource=per_resource,
    )


# ---------------------------------------------------------------------------
# Result builders
# ---------------------------------------------------------------------------

def _build_baseline(areas: Dict[str, AreaInfo]) -> dict:
    """Baseline = keep everything where it is (no movement)."""
    total_current = 0
    total_required = 0
    total_deficit = 0
    per_res: Dict[str, dict] = {}
    for res in RESOURCES:
        c = sum(a.current.get(res, 0) for a in areas.values())
        r = sum(a.required.get(res, 0) for a in areas.values())
        d = sum(a.deficit.get(res, 0) for a in areas.values())
        per_res[res] = {
            "total_current": c,
            "total_required": r,
            "total_deficit": d,
            "total_surplus": sum(a.surplus.get(res, 0) for a in areas.values()),
        }
        total_current += c
        total_required += r
        total_deficit += d
    return {
        "description": "FIXED ALLOCATION - all resources stay in their current area",
        "total_current": total_current,
        "total_required": total_required,
        "total_deficit": total_deficit,
        "total_movement_cost": 0.0,
        "total_resources_moved": 0,
        "per_resource": per_res,
    }


def _build_movements(
    solution:  Dict[Tuple[str, str, str], int],
    areas:     Dict[str, AreaInfo],
    distances: Dict[Tuple[str, str], float],
    cost_w:    Dict[str, float],
    benefit:   Dict[str, Dict[str, float]],
) -> List[Movement]:
    movements: List[Movement] = []
    for (f, t, res), q in sorted(solution.items()):
        dist = distances[(f, t)]
        cost = round(q * dist * cost_w[res], 2)
        # Prototype risk benefit: quantity filled x recipient priority.
        # recipient_priority = benefit[t,res] (already a weighted blend of
        # risk, deficit, population, vulnerability, all in [0,1]).
        risk_reduction = round(q * benefit[res][t], 2)
        reason = (
            f"{areas[t].area_name} needs {res} "
            f"(deficit {areas[t].deficit[res]}, risk "
            f"{areas[t].predicted_risk:.1f}, vuln "
            f"{areas[t].vulnerability:.2f}); "
            f"{areas[f].area_name} has surplus {areas[f].surplus[res]}; "
            f"distance {dist:.0f} km"
        )
        movements.append(Movement(
            resource=res,
            from_area=areas[f].area_name,
            to_area=areas[t].area_name,
            quantity=q,
            distance=dist,
            movement_cost=cost,
            reason=reason,
            estimated_risk_reduction=risk_reduction,
        ))
    return movements


def _final_states(
    areas:    Dict[str, AreaInfo],
    solution: Dict[Tuple[str, str, str], int],
) -> List[AreaFinalState]:
    states: List[AreaFinalState] = []
    for a_id in sorted(areas.keys()):
        a = areas[a_id]
        for res in RESOURCES:
            inbound  = sum(q for (f, t, r), q in solution.items()
                           if t == a_id and r == res)
            outbound = sum(q for (f, t, r), q in solution.items()
                           if f == a_id and r == res)
            initial = a.current.get(res, 0)
            final   = initial + inbound - outbound
            required = a.required.get(res, 0)
            rem_def  = max(0, required - final)
            rem_sur  = max(0, final - required)
            states.append(AreaFinalState(
                area_id=a_id,
                area_name=a.area_name,
                resource=res,
                initial_quantity=initial,
                inbound=inbound,
                outbound=outbound,
                final_quantity=final,
                required_quantity=required,
                remaining_deficit=rem_def,
                remaining_surplus=rem_sur,
            ))
    return states


def _remaining_deficits(
    areas:    Dict[str, AreaInfo],
    solution: Dict[Tuple[str, str, str], int],
) -> List[dict]:
    out: List[dict] = []
    for st in _final_states(areas, solution):
        if st.remaining_deficit > 0:
            out.append({
                "area_id": st.area_id,
                "area_name": st.area_name,
                "resource": st.resource,
                "remaining_deficit": st.remaining_deficit,
            })
    return out


def _per_resource_summary(
    areas:     Dict[str, AreaInfo],
    solution:  Dict[Tuple[str, str, str], int],
    distances: Dict[Tuple[str, str], float],
    cost_w:    Dict[str, float],
) -> Dict[str, dict]:
    summary: Dict[str, dict] = {}
    for res in RESOURCES:
        moved = sum(q for (f, t, r), q in solution.items() if r == res)
        cost  = sum(
            q * distances[(f, t)] * cost_w[res]
            for (f, t, r), q in solution.items() if r == res
        )
        rem_def = sum(
            max(0, a.required.get(res, 0) - (
                a.current.get(res, 0)
                + sum(q for (f, t, r), q in solution.items()
                      if t == a.area_id and r == res)
                - sum(q for (f, t, r), q in solution.items()
                      if f == a.area_id and r == res)
            ))
            for a in areas.values()
        )
        summary[res] = {
            "total_moved": moved,
            "total_movement_cost": round(cost, 2),
            "remaining_deficit": rem_def,
        }
    return summary


# ---------------------------------------------------------------------------
# High-level entry point (consumes Phase 5 directly)
# ---------------------------------------------------------------------------

def run_optimizer(
    as_of:           Optional[str] = None,
    prefer_forecast: bool = True,
    risk_by_area:    Optional[Dict[str, float]] = None,
) -> OptimizationResult:
    """
    End-to-end: Phase 5 demand state -> OR-Tools allocation.

    Reuses Phase 5 functions; does not re-implement any of their logic.
    """
    from backend.risk.resource_demand import (
        calculate_resource_requirements,
        get_risk_inputs,
        load_area_static,
    )

    if risk_by_area is None:
        risk_by_area, _ = get_risk_inputs(
            as_of=as_of, prefer_forecast=prefer_forecast
        )

    requirements = calculate_resource_requirements(risk_by_area)
    area_static  = load_area_static()
    areas        = build_area_infos(requirements, area_static)
    distances    = load_distances()

    return optimize_resource_allocation(areas, distances)
