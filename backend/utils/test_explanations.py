"""
test_explanations.py
====================
Phase 10 executable test - verifies the human-readable explanation engine and
its API endpoint. No internet access required.

Usage (from project root):
    python backend/utils/test_explanations.py
"""

from __future__ import annotations

import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from backend.utils.explanations import (          # noqa: E402
    DISCLAIMER,
    explain_area_risk,
    explain_resource_shortages,
    explain_transfer,
    explain_allocation_comparison,
    explain_scenario,
    build_explanations,
)
from backend.risk import run_risk_engine          # noqa: E402
from backend.risk.resource_demand import (        # noqa: E402
    RESOURCES,
    RESOURCES_CSV,
    calculate_resource_requirements,
    get_risk_inputs,
)
from backend.optimization.optimizer import (      # noqa: E402
    build_area_infos,
    load_distances,
    optimize_resource_allocation,
)
from backend.risk.resource_demand import load_area_static  # noqa: E402
from backend.analysis.comparison import compare_allocations  # noqa: E402

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


def _gather():
    """Run the existing engines once and return the inputs for explanations."""
    risk_by_area, _ = get_risk_inputs()
    phase3 = {r.area_id: r.to_dict() for r in run_risk_engine()}
    reqs = calculate_resource_requirements(risk_by_area)
    areas = load_area_static()
    opt = optimize_resource_allocation(
        build_area_infos(reqs, areas), load_distances()
    )
    comparison = compare_allocations(risk_by_area=risk_by_area, optimizer_result=opt)
    movements = [
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
    ]
    return phase3, reqs, opt, comparison, movements


def run_tests() -> int:
    results = []

    def check(name: str, cond: bool, detail: str = "") -> None:
        results.append((name, bool(cond), detail))

    hashes_before = {
        "climate_history.csv": _sha256(_CLIMATE_CSV),
        "areas.csv": _sha256(_AREAS_CSV),
        "distances.csv": _sha256(_DISTANCES_CSV),
        "resources.csv": _sha256(RESOURCES_CSV),
        "model.pkl": _sha256(_MODEL_PKL),
    }

    phase3, reqs, opt, comparison, movements = _gather()

    # 1. area-risk explanations for all 8 areas
    risk_exps = [explain_area_risk(phase3[a]) for a in sorted(phase3)]
    check("1. area-risk explanations for all 8 areas",
          {e["area_id"] for e in risk_exps} == EXPECTED_AREAS
          and all(isinstance(e["explanation"], str) and e["explanation"] for e in risk_exps))

    # 2. resource-deficit explanations with correct names/quantities
    short = explain_resource_shortages([r.to_dict() for r in reqs])
    # verify a known deficit quantity is reproduced
    some_deficit = [r for r in reqs if r.deficit > 0]
    if some_deficit:
        r0 = some_deficit[0]
        found = False
        for a in short["areas"]:
            if a["area_id"] != r0.area_id:
                continue
            for s in a["shortages"]:
                if s["resource"] == r0.resource and s["deficit"] == r0.deficit:
                    found = True
        check("2. resource-deficit explanation correct qty", found,
              f"expected {r0.area_id}/{r0.resource} deficit {r0.deficit}")
    else:
        check("2. resource-deficit explanation correct qty", True)

    # 3. transfer explanations for valid optimizer movements
    if movements:
        t_exps = [explain_transfer(m) for m in movements]
        check("3. transfer explanations for valid movements",
              len(t_exps) == len(movements)
              and all(e["quantity"] and e["explanation"] for e in t_exps))
        # no self-transfer explanations
        check("3. no self-transfer in explanations",
              all(e["from_area"] != e["to_area"] for e in t_exps))
    else:
        check("3. transfer explanations for valid movements", True)
        check("3. no self-transfer in explanations", True)

    # 4. allocation comparison explanation (improved + worsened)
    comp_exp = explain_allocation_comparison(comparison)
    check("4. comparison explanation present",
          isinstance(comp_exp["explanation"], str) and comp_exp["explanation"])
    # improved/worsened must partition the nonzero-change areas
    nonzero = [a for a in comparison["area_results"]
               if a["impact_change"] not in (0, 0.0)]
    listed = set(comp_exp["improved_areas"]) | set(comp_exp["worsened_areas"])
    # names present for at least the areas that changed
    check("4. improved/worsened areas listed",
          len(comp_exp["improved_areas"]) + len(comp_exp["worsened_areas"])
          == len(nonzero),
          f"nonzero={len(nonzero)} listed={len(listed)}")

    # 5. scenario explanation using real Phase 7 output
    from backend.simulation.scenarios import ScenarioParams, run_scenario
    scen = run_scenario(ScenarioParams(rainfall_change_pct=30))
    scen_exp = explain_scenario(scen)
    check("5. scenario explanation present",
          isinstance(scen_exp["explanation"], str) and scen_exp["explanation"])

    # 6. missing / malformed fields -> limitation, no fabrication
    bad_risk = explain_area_risk({})
    check("6a. malformed risk -> limitation",
          bad_risk["limitation"] is not None and "risk" in bad_risk["explanation"].lower())
    bad_short = explain_resource_shortages([])
    check("6b. empty requirements -> limitation",
          bad_short["limitation"] is not None)
    bad_move = explain_transfer({"resource": "pumps"})
    check("6c. partial movement -> limitation",
          bad_move["limitation"] is not None)
    bad_comp = explain_allocation_comparison({})
    check("6d. empty comparison -> limitation",
          bad_comp["limitation"] is not None)

    # 7. deterministic for identical inputs
    a1 = build_explanations(
        risk_results=[phase3[a] for a in sorted(phase3)],
        requirements=[r.to_dict() for r in reqs],
        movements=movements,
        comparison=comparison,
    )
    a2 = build_explanations(
        risk_results=[phase3[a] for a in sorted(phase3)],
        requirements=[r.to_dict() for r in reqs],
        movements=movements,
        comparison=comparison,
    )
    check("7. deterministic output",
          json.dumps(a1, sort_keys=True) == json.dumps(a2, sort_keys=True))

    # 8. API /explanations valid structure + invalid behaviour
    from fastapi.testclient import TestClient
    from backend.api.main import app
    client = TestClient(app)
    resp = client.get("/explanations")
    ok = resp.status_code == 200
    body = resp.json() if ok else {}
    if ok:
        ok = (
            "disclaimer" in body
            and "area_risk" in body
            and "resource_shortages" in body
            and "allocation_comparison" in body
            and len(body["area_risk"]) == 8
        )
    check("8a. API /explanations 200 + structure", ok,
          f"status={resp.status_code}")
    # existing endpoints still compatible
    check("8b. /health still ok", client.get("/health").json().get("status") == "ok")
    check("8c. /risk still 8", len(client.get("/risk").json().get("areas", [])) == 8)
    check("8d. /comparison still 200", client.get("/comparison").status_code == 200)

    # 9. source files unchanged
    hashes_after = {
        "climate_history.csv": _sha256(_CLIMATE_CSV),
        "areas.csv": _sha256(_AREAS_CSV),
        "distances.csv": _sha256(_DISTANCES_CSV),
        "resources.csv": _sha256(RESOURCES_CSV),
        "model.pkl": _sha256(_MODEL_PKL),
    }
    check("9. source CSVs/model unchanged", hashes_before == hashes_after)

    # ---- report ----
    print("=" * 64)
    print("PHASE 10 - EXPLANATION ENGINE TEST")
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
