"""
test_comparison.py
==================
Phase 9 executable test - verifies the fixed-vs-optimized comparison engine
with a 15-point validation suite. No internet access required.

Usage (from project root):
    python backend\analysis\test_comparison.py
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from backend.analysis.comparison import (          # noqa: E402
    compare_allocations,
    _apply_movements,
)
from backend.optimization.optimizer import (       # noqa: E402
    Movement,
    OptimizationResult,
)
from backend.risk.resource_demand import (         # noqa: E402
    RESOURCES,
    RESOURCES_CSV,
    load_area_static,
    load_inventory,
    get_risk_inputs,
)

_DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"
)
_CLIMATE_CSV = os.path.join(_DATA_DIR, "climate_history.csv")
_AREAS_CSV = os.path.join(_DATA_DIR, "areas.csv")
_DISTANCES_CSV = os.path.join(_DATA_DIR, "distances.csv")
_MODEL_PKL = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "forecasting", "models", "flood_risk_model.pkl",
)
EXPECTED_AREAS = {"IND", "UJJ", "DEW", "DHA", "RAT", "MAN", "MHO", "SEH"}


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        h.update(fh.read())
    return h.hexdigest()


def _finite_nonneg(x) -> bool:
    if not isinstance(x, (int, float)):
        return False
    return math.isfinite(x) and x >= 0


def run_tests() -> int:
    results = []

    def check(name: str, cond: bool, detail: str = "") -> None:
        results.append((name, bool(cond), detail))

    # Hash source files before
    hashes_before = {
        "climate_history.csv": _sha256(_CLIMATE_CSV),
        "areas.csv": _sha256(_AREAS_CSV),
        "distances.csv": _sha256(_DISTANCES_CSV),
        "resources.csv": _sha256(RESOURCES_CSV),
        "model.pkl": _sha256(_MODEL_PKL),
    }

    # Run comparison (twice for determinism)
    comp1 = compare_allocations()
    comp2 = compare_allocations()

    # 1. all eight areas
    area_ids = {a["area_id"] for a in comp1["area_results"]}
    check("1. comparison returns all 8 areas", area_ids == EXPECTED_AREAS,
          f"got {sorted(area_ids)}")

    # 2. fixed & optimized impact finite and nonnegative
    check("2. fixed impact finite/nonneg",
          _finite_nonneg(comp1["fixed_risk_impact"]),
          f"got {comp1['fixed_risk_impact']}")
    check("2. optimized impact finite/nonneg",
          _finite_nonneg(comp1["optimized_risk_impact"]),
          f"got {comp1['optimized_risk_impact']}")

    # 3. per-area required fields
    required_fields = {
        "area_id", "area_name", "predicted_risk", "fixed_risk_impact",
        "optimized_risk_impact", "fixed_total_deficit",
        "optimized_total_deficit", "impact_change",
    }
    ok = all(required_fields <= set(a.keys()) for a in comp1["area_results"])
    check("3. per-area results contain required fields", ok)

    # 4. resource deficits nonnegative
    ok = all(
        a["fixed_total_deficit"] >= 0 and a["optimized_total_deficit"] >= 0
        for a in comp1["area_results"]
    )
    ok = ok and all(
        v["fixed_deficit"] >= 0 and v["optimized_deficit"] >= 0
        for v in comp1["resource_totals"].values()
    )
    check("4. resource deficits nonnegative", ok)

    # 5. optimized inventory never negative
    ok = all(
        pr["current"] >= 0
        for a in comp1["area_results"]
        for pr in a["optimized_per_resource"].values()
    )
    check("5. optimized inventory never negative", ok)

    # 6. resource quantities integers
    ok = all(
        isinstance(pr["current"], int) and isinstance(pr["required"], int)
        and isinstance(pr["deficit"], int) and isinstance(pr["surplus"], int)
        for a in comp1["area_results"]
        for pr in list(a["fixed_per_resource"].values())
        + list(a["optimized_per_resource"].values())
    )
    check("6. resource quantities are integers", ok)

    # 7. total quantity of each resource conserved
    ok = True
    for res in RESOURCES:
        ft = comp1["resource_totals"][res]
        fixed_total = sum(
            a["fixed_per_resource"][res]["current"]
            for a in comp1["area_results"]
        )
        opt_total = sum(
            a["optimized_per_resource"][res]["current"]
            for a in comp1["area_results"]
        )
        if not (ft["total_current"] == fixed_total == opt_total):
            ok = False
    check("7. total quantity of each resource conserved", ok)

    # 8. donor constraints respected (each movement qty <= donor fixed current)
    fixed_cur = {
        a["area_id"]: a["fixed_per_resource"] for a in comp1["area_results"]
    }
    static = load_area_static()
    id_to_name = {aid: s["area_name"] for aid, s in static.items()}
    ok = True
    for m in comp1["optimization_summary"]["movements"]:
        donor_id = next(
            (aid for aid, nm in id_to_name.items() if nm == m["from_area"]),
            None,
        )
        donor_cur = fixed_cur[donor_id][m["resource"]]["current"]
        if m["quantity"] > donor_cur:
            ok = False
    check("8. donor constraints respected", ok)

    # 9. no self-transfers
    ok = all(
        m["from_area"] != m["to_area"]
        for m in comp1["optimization_summary"]["movements"]
    )
    check("9. no self-transfers in recommendations", ok)

    # 10. deterministic
    check("10. deterministic results",
          json.dumps(comp1, sort_keys=True) == json.dumps(comp2, sort_keys=True))

    # 11. source files unchanged
    hashes_after = {
        "climate_history.csv": _sha256(_CLIMATE_CSV),
        "areas.csv": _sha256(_AREAS_CSV),
        "distances.csv": _sha256(_DISTANCES_CSV),
        "resources.csv": _sha256(RESOURCES_CSV),
        "model.pkl": _sha256(_MODEL_PKL),
    }
    check("11. source CSVs/model unchanged", hashes_before == hashes_after)

    # 12. zero fixed impact -> no division by zero
    zero_risk = {aid: 0.0 for aid in EXPECTED_AREAS}
    try:
        comp_zero = compare_allocations(risk_by_area=zero_risk)
        ok = (
            _finite_nonneg(comp_zero["fixed_risk_impact"])
            and _finite_nonneg(comp_zero["percentage_reduction"])
            and comp_zero["fixed_risk_impact"] == 0.0
        )
    except ZeroDivisionError:
        ok = False
    check("12. zero fixed impact safe (no div-by-zero)", ok)

    # 13. empty movement list handled
    from backend.risk.resource_demand import (
        calculate_resource_requirements,
    )
    from backend.optimization.optimizer import (
        build_area_infos,
        load_distances,
    )
    risk, _ = get_risk_inputs()
    reqs = calculate_resource_requirements(risk)
    areas = build_area_infos(reqs, load_area_static())
    dist = load_distances()
    empty_result = OptimizationResult(
        feasible=True, status="OPTIMAL", objective_value=0.0,
        total_movement_cost=0.0, total_resources_moved=0,
        total_movements=0, estimated_risk_reduction=0.0,
        movements=[], area_states=[], remaining_deficits=[],
        baseline=reqs, per_resource={},
    )
    try:
        comp_empty = compare_allocations(optimizer_result=empty_result)
        # with no moves, optimized == fixed
        ok = (
            comp_empty["fixed_risk_impact"] == comp_empty["optimized_risk_impact"]
            and comp_empty["optimization_summary"]["total_movements"] == 0
        )
    except Exception as e:
        ok = False
        print(f"   (empty-movement error: {e})")
    check("13. empty movement list handled", ok)

    # 14. invalid optimizer result -> clear error
    # (a) infeasible result
    infeasible = OptimizationResult(
        feasible=False, status="INFEASIBLE", objective_value=0.0,
        total_movement_cost=0.0, total_resources_moved=0,
        total_movements=0, estimated_risk_reduction=0.0,
        movements=[], area_states=[], remaining_deficits=[],
        baseline=[], per_resource={},
    )
    try:
        compare_allocations(optimizer_result=infeasible)
        ok = False
    except ValueError:
        ok = True
    # (b) movement that exceeds donor availability
    bad_move = Movement(
        resource="pumps", from_area="Indore", to_area="Ujjain",
        quantity=99999, distance=1.0, movement_cost=1.0,
        reason="test", estimated_risk_reduction=0.0,
    )
    bad_result = OptimizationResult(
        feasible=True, status="OPTIMAL", objective_value=0.0,
        total_movement_cost=0.0, total_resources_moved=99999,
        total_movements=1, estimated_risk_reduction=0.0,
        movements=[bad_move], area_states=[], remaining_deficits=[],
        baseline=[], per_resource={},
    )
    try:
        compare_allocations(optimizer_result=bad_result)
        ok = False
    except ValueError:
        pass  # expected
    check("14. invalid optimizer result -> clear error", ok)

    # 15. API /comparison endpoint returns 200 + structure
    try:
        from fastapi.testclient import TestClient
        from backend.api.main import app
        client = TestClient(app)
        resp = client.get("/comparison")
        ok = resp.status_code == 200
        if ok:
            body = resp.json()
            required_top = {
                "metric_name", "fixed_risk_impact", "optimized_risk_impact",
                "absolute_reduction", "percentage_reduction",
                "area_results", "resource_totals", "optimization_summary",
                "assumptions", "limitations",
            }
            ok = required_top <= set(body.keys())
            ok = ok and len(body["area_results"]) == 8
    except Exception as e:
        ok = False
        print(f"   (API /comparison error: {e})")
    check("15. API /comparison endpoint 200 + structure", ok)

    # ---- report ----
    print("=" * 64)
    print("PHASE 9 - FIXED VS OPTIMIZED COMPARISON TEST")
    print("=" * 64)
    passed = 0
    for name, ok, detail in results:
        mark = "PASS" if ok else "FAIL"
        if ok:
            passed += 1
        line = f"[{mark}] {name}"
        if detail and not ok:
            line += f"  ({detail})"
        print(line)
    print("-" * 64)
    print(f"RESULT: {passed}/{len(results)} checks passed")
    print("=" * 64)
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(run_tests())
