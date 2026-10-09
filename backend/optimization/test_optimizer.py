"""
test_optimizer.py
=================
Phase 6 sanity check — runs the OR-Tools resource-allocation optimizer on the
Phase 5 demand state and prints movements, totals, remaining deficits and the
final per-area resource state.  Also runs a 15-point validation suite.

No pytest required — plain print-based verification suitable for a demo.

Usage (from project root):
    python backend\\optimization\\test_optimizer.py
    python -m backend.optimization.test_optimizer
    python backend\\optimization\\test_optimizer.py --as-of "2024-11-30 18:00:00"
    python backend\\optimization\\test_optimizer.py --no-forecast

Output is ASCII-only so it never crashes the Windows cp1252 console.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from backend.optimization.optimizer import (          # noqa: E402
    RESOURCES,
    load_distances,
    run_optimizer,
)
from backend.risk.resource_demand import (           # noqa: E402
    RESOURCES_CSV,
    load_inventory,
    load_area_static,
)


def _csv_sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        h.update(fh.read())
    return h.hexdigest()


def _validate(result, areas, distances, resources_csv_path) -> List[str]:
    """Run the 15-point validation suite. Returns list of error strings."""
    errors: List[str] = []

    # 1. Solver executed successfully
    if not result.feasible:
        errors.append(f"1. solver did not reach a feasible solution ({result.status})")

    # 2. Result is feasible (movements exist only if feasible)
    if result.feasible and result.status not in ("OPTIMAL", "FEASIBLE"):
        errors.append(f"2. unexpected status {result.status}")

    area_ids = set(areas.keys())

    for m in result.movements:
        # 3. integer quantities
        if m.quantity != int(m.quantity):
            errors.append(f"3. non-integer quantity {m.quantity} "
                          f"({m.resource} {m.from_area}->{m.to_area})")
        # 4. no negative movements
        if m.quantity < 0:
            errors.append(f"4. negative movement {m.quantity} "
                          f"({m.resource} {m.from_area}->{m.to_area})")
        # 9. no self-moves
        if m.from_area == m.to_area:
            errors.append(f"9. self-move {m.from_area} -> {m.to_area}")
        # 10. route exists in distances.csv
        f_id = next((a.area_id for a in areas.values()
                     if a.area_name == m.from_area), None)
        t_id = next((a.area_id for a in areas.values()
                     if a.area_name == m.to_area), None)
        if (f_id, t_id) not in distances:
            errors.append(f"10. route {m.from_area}->{m.to_area} "
                          f"not in distances.csv")

    # 5. donors never send more than surplus
    for a in areas.values():
        for res in RESOURCES:
            out = sum(m.quantity for m in result.movements
                      if m.resource == res and m.from_area == a.area_name)
            if out > a.surplus.get(res, 0):
                errors.append(f"5. {a.area_id} sends {out} {res} "
                              f"> surplus {a.surplus.get(res, 0)}")

    # 6. recipients never receive more than deficit
    for a in areas.values():
        for res in RESOURCES:
            inc = sum(m.quantity for m in result.movements
                      if m.resource == res and m.to_area == a.area_name)
            if inc > a.deficit.get(res, 0):
                errors.append(f"6. {a.area_id} receives {inc} {res} "
                              f"> deficit {a.deficit.get(res, 0)}")

    # 7. deficit areas do not donate that resource
    for a in areas.values():
        for res in RESOURCES:
            if a.deficit.get(res, 0) > 0:
                out = sum(m.quantity for m in result.movements
                          if m.resource == res and m.from_area == a.area_name)
                if out > 0:
                    errors.append(f"7. deficit area {a.area_id} donates "
                                  f"{out} {res}")

    # 8. resources are conserved (final = initial + in - out; total preserved)
    inv = load_inventory(resources_csv_path)
    for res in RESOURCES:
        csv_total = sum(inv[aid]["current"][res] for aid in inv)
        final_total = sum(st.final_quantity for st in result.area_states
                          if st.resource == res)
        if csv_total != final_total:
            errors.append(f"8. {res} not conserved "
                          f"(csv={csv_total}, final={final_total})")

    # 11. final quantities non-negative
    for st in result.area_states:
        if st.final_quantity < 0:
            errors.append(f"11. negative final quantity "
                          f"{st.area_id}/{st.resource}={st.final_quantity}")

    # 12. remaining deficits non-negative
    for st in result.area_states:
        if st.remaining_deficit < 0:
            errors.append(f"12. negative remaining deficit "
                          f"{st.area_id}/{st.resource}")
        if st.remaining_surplus < 0:
            errors.append(f"12. negative remaining surplus "
                          f"{st.area_id}/{st.resource}")

    # 13. determinism is checked by the caller (two runs compared)

    # 14. baseline unchanged (no movement in baseline)
    if result.baseline["total_resources_moved"] != 0:
        errors.append("14. baseline has non-zero movement")
    if result.baseline["total_movement_cost"] != 0.0:
        errors.append("14. baseline has non-zero cost")

    # 15. source CSV unmodified (checked by caller via hash comparison)

    return errors


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 6 optimizer test")
    parser.add_argument("--as-of", default=None,
                        help='Timestamp, e.g. "2024-11-30 18:00:00".')
    parser.add_argument("--no-forecast", action="store_true",
                        help="Use Phase 3 current risk instead of Phase 4.")
    args = parser.parse_args()

    print("=" * 92)
    print("PHASE 6 - RESOURCE ALLOCATION OPTIMIZATION  (OR-Tools)")
    print("=" * 92)

    # Hash source CSVs before
    h_resources_before = _csv_sha256(RESOURCES_CSV)

    result = run_optimizer(
        as_of=args.as_of, prefer_forecast=not args.no_forecast
    )
    areas = build_areas_for_validation()
    distances = load_distances()

    print(f"Solver status        : {result.status}")
    print(f"Objective value      : {result.objective_value:.2f}")
    print()

    # ---- Movements table ----------------------------------------------------
    print("RESOURCE OPTIMIZATION")
    print(f"{'Resource':<14} {'From':<11} {'To':<11} {'Qty':>4} "
          f"{'Dist':>7} {'Cost':>8}")
    print("-" * 64)
    if not result.movements:
        print("  (no movements recommended)")
    for m in result.movements:
        print(f"{m.resource:<14} {m.from_area:<11} {m.to_area:<11} "
              f"{m.quantity:>4} {m.distance:>7.0f} {m.movement_cost:>8.1f}")
    print("-" * 64)
    print()

    print(f"Total resources moved : {result.total_resources_moved}")
    print(f"Total movement cost   : {result.total_movement_cost:.1f} "
          f"(prototype cost units)")
    print(f"Estimated prototype risk benefit : "
          f"{result.estimated_risk_reduction:.1f}")
    print()

    # ---- Remaining deficits -------------------------------------------------
    print("REMAINING DEFICITS")
    print(f"{'Area':<11} {'Resource':<14} {'Remaining Deficit':>18}")
    print("-" * 48)
    if not result.remaining_deficits:
        print("  (all deficits fully covered)")
    for d in result.remaining_deficits:
        print(f"{d['area_name']:<11} {d['resource']:<14} "
              f"{d['remaining_deficit']:>18}")
    print()

    # ---- Final resource state -----------------------------------------------
    print("FINAL RESOURCE STATE")
    print(f"{'Area':<11} {'Resource':<14} {'Initial':>7} {'In':>4} "
          f"{'Out':>4} {'Final':>6} {'Required':>9}")
    print("-" * 60)
    last = None
    for st in result.area_states:
        if last is not None and st.area_id != last:
            print()
        last = st.area_id
        print(f"{st.area_name:<11} {st.resource:<14} "
              f"{st.initial_quantity:>7} {st.inbound:>4} {st.outbound:>4} "
              f"{st.final_quantity:>6} {st.required_quantity:>9}")
    print("-" * 60)
    print()

    # ---- Per-resource summary -----------------------------------------------
    print("PER-RESOURCE SUMMARY")
    for res in RESOURCES:
        s = result.per_resource[res]
        print(f"  {res:<14} moved={s['total_moved']:<4} "
              f"cost={s['total_movement_cost']:<8.1f} "
              f"remaining_deficit={s['remaining_deficit']}")
    print()

    # ---- Baseline -----------------------------------------------------------
    b = result.baseline
    print("BASELINE (FIXED ALLOCATION - no movement)")
    print(f"  total_current   : {b['total_current']}")
    print(f"  total_required  : {b['total_required']}")
    print(f"  total_deficit   : {b['total_deficit']}")
    print(f"  total_moved     : {b['total_resources_moved']}")
    print(f"  total_cost      : {b['total_movement_cost']}")
    print()

    # ---- Validation ---------------------------------------------------------
    errors = _validate(result, areas, distances, RESOURCES_CSV)

    # 13. determinism: run again and compare
    result2 = run_optimizer(
        as_of=args.as_of, prefer_forecast=not args.no_forecast
    )
    key1 = json.dumps(_fingerprint(result), sort_keys=True)
    key2 = json.dumps(_fingerprint(result2), sort_keys=True)
    if key1 != key2:
        errors.append("13. optimizer is NOT deterministic across runs")

    # 15. source CSV unmodified
    h_resources_after = _csv_sha256(RESOURCES_CSV)
    if h_resources_before != h_resources_after:
        errors.append("15. resources.csv was modified by the optimizer")

    if errors:
        print("VALIDATION FAILURES:")
        for e in errors:
            print(f"  FAIL  {e}")
        sys.exit(1)

    print("VALIDATIONS PASSED (15/15)")
    print("  1. OR-Tools solver executed successfully")
    print("  2. result is feasible")
    print("  3. movement quantities are integers")
    print("  4. no negative movements")
    print("  5. donors never send more than surplus")
    print("  6. recipients never receive more than deficit")
    print("  7. deficit areas do not donate that resource")
    print("  8. resources are conserved (total matches resources.csv)")
    print("  9. no area sends resources to itself")
    print(" 10. all routes exist in distances.csv")
    print(" 11. final quantities are non-negative")
    print(" 12. remaining deficits are non-negative")
    print(" 13. optimizer is deterministic (two runs identical)")
    print(" 14. baseline remains unchanged (no movement)")
    print(" 15. source CSV unmodified (SHA-256 identical)")
    print()
    print("NOTE: This optimizer is a prototype decision-support model.")
    print("Movement costs and risk benefits are estimated values for")
    print("demonstration and are not real emergency logistics costs or")
    print("guaranteed disaster outcomes.")
    print()
    print("Done.")


def build_areas_for_validation():
    """Rebuild the same AreaInfo dict the optimizer used (for validation)."""
    from backend.optimization.optimizer import build_area_infos
    from backend.risk.resource_demand import (
        calculate_resource_requirements,
        get_risk_inputs,
    )
    risk_by_area, _ = get_risk_inputs()
    requirements = calculate_resource_requirements(risk_by_area)
    area_static = load_area_static()
    return build_area_infos(requirements, area_static)


def _fingerprint(result) -> dict:
    """Compact deterministic fingerprint of an OptimizationResult."""
    return {
        "status": result.status,
        "objective": round(result.objective_value, 6),
        "total_cost": round(result.total_movement_cost, 6),
        "total_moved": result.total_resources_moved,
        "movements": sorted(
            (m.resource, m.from_area, m.to_area, m.quantity)
            for m in result.movements
        ),
        "final": sorted(
            (st.area_id, st.resource, st.final_quantity)
            for st in result.area_states
        ),
    }


if __name__ == "__main__":
    main()
