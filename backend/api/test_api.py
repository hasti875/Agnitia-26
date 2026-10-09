"""
test_api.py
===========
Phase 8 API tests — exercises all six endpoints via FastAPI TestClient and
runs a 17-point validation suite. No internet access required.

Usage (from project root):
    python backend\\api\\test_api.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from fastapi.testclient import TestClient  # noqa: E402

from backend.api.main import app  # noqa: E402
from backend.risk.resource_demand import RESOURCES  # noqa: E402

EXPECTED_AREAS = {"IND", "UJJ", "DEW", "DHA", "RAT", "MAN", "MHO", "SEH"}


def run_tests() -> int:
    client = TestClient(app)
    results = []

    def check(name: str, cond: bool, detail: str = "") -> None:
        results.append((name, cond, detail))

    # 1. /health
    r = client.get("/health")
    check("1. /health 200", r.status_code == 200, f"got {r.status_code}")
    check("1. /health status ok", r.json().get("status") == "ok")

    # 2. /areas -> exactly 8
    r = client.get("/areas")
    areas = r.json().get("areas", [])
    check("2. /areas 200", r.status_code == 200)
    check("2. /areas exactly 8", len(areas) == 8, f"got {len(areas)}")
    check("2. /areas ids valid",
          {a["area_id"] for a in areas} == EXPECTED_AREAS)

    # 3. /risk -> exactly 8
    r = client.get("/risk")
    risk = r.json().get("areas", [])
    check("3. /risk 200", r.status_code == 200)
    check("3. /risk exactly 8", len(risk) == 8, f"got {len(risk)}")

    # 4. risk values numeric 0-100
    ok = all(
        isinstance(a["predicted_risk"], (int, float))
        and 0.0 <= a["predicted_risk"] <= 100.0
        for a in risk
    )
    check("4. risk values numeric 0-100", ok)

    # 5. /resources valid combinations
    r = client.get("/resources")
    res = r.json().get("resources", [])
    check("5. /resources 200", r.status_code == 200)
    check("5. /resources 24 rows (8x3)", len(res) == 24, f"got {len(res)}")
    combos = {(x["area_id"], x["resource"]) for x in res}
    check("5. /resources all 8x3 combos",
          len(combos) == 24 and
          {c[0] for c in combos} == EXPECTED_AREAS and
          {c[1] for c in combos} == set(RESOURCES))

    # 6. resource values nonnegative integers
    ok = all(
        isinstance(x["current"], int) and isinstance(x["required"], int)
        and isinstance(x["deficit"], int) and isinstance(x["surplus"], int)
        and x["current"] >= 0 and x["required"] >= 0
        and x["deficit"] >= 0 and x["surplus"] >= 0
        for x in res
    )
    check("6. resource values nonnegative ints", ok)

    # 7. /recommendations valid
    r = client.get("/recommendations")
    rec = r.json()
    check("7. /recommendations 200", r.status_code == 200)
    check("7. /recommendations feasible", rec.get("feasible") is True)
    check("7. /recommendations has movements key", "movements" in rec)

    # 8. recommendation quantities positive ints
    moves = rec.get("movements", [])
    ok = all(
        isinstance(m["quantity"], int) and m["quantity"] > 0 for m in moves
    )
    check("8. recommendation quantities positive ints", ok,
          f"{len(moves)} movements")

    # 9. no self-transfers
    ok = all(m["from_area"] != m["to_area"] for m in moves)
    check("9. no self-transfers", ok)

    # 10-12. /simulate valid scenarios
    for label, payload in [
        ("10. rainfall 30", {"rainfall_change_pct": 30}),
        ("11. river-level 20", {"river_level_change_pct": 20}),
        ("12. resources -30", {"resource_availability_change_pct": -30}),
    ]:
        r = client.post("/simulate", json=payload)
        check(f"{label} succeeds", r.status_code == 200,
              f"got {r.status_code}")

    # 13-15. invalid values -> 4xx
    for label, payload in [
        ("13. rainfall 99", {"rainfall_change_pct": 99}),
        ("14. river-level 50", {"river_level_change_pct": 50}),
        ("15. resources -50", {"resource_availability_change_pct": -50}),
    ]:
        r = client.post("/simulate", json=payload)
        check(f"{label} returns 4xx", 400 <= r.status_code < 500,
              f"got {r.status_code}")

    # 16. scenario results contain all 8 areas
    r = client.post("/simulate", json={"rainfall_change_pct": 30})
    body = r.json()
    scen_risk = body.get("scenario_result", {}).get("risk", [])
    area_ids = {a["area_id"] for a in scen_risk}
    check("16. scenario contains all 8 areas", area_ids == EXPECTED_AREAS,
          f"got {area_ids}")

    # 17. Phase 3-7 regression is run separately by the caller; here we
    # confirm the API did not crash any engine (all endpoints returned 200).
    check("17. all core endpoints returned 200",
          all(c for name, c, _ in results if name.split(".")[0] in
              {"1", "2", "3", "5", "7"}))

    # ---- Report ------------------------------------------------------------
    passed = sum(1 for _, c, _ in results if c)
    failed = len(results) - passed
    print("=" * 70)
    print("PHASE 8 API TESTS")
    print("=" * 70)
    for name, cond, detail in results:
        mark = "PASS" if cond else "FAIL"
        extra = f"  ({detail})" if detail and not cond else ""
        print(f"  [{mark}] {name}{extra}")
    print("-" * 70)
    print(f"Total: {len(results)}  Passed: {passed}  Failed: {failed}")
    print("=" * 70)

    if failed:
        sys.exit(1)
    print("All API tests passed.")
    return passed


if __name__ == "__main__":
    run_tests()
