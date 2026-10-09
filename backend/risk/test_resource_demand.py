"""
test_resource_demand.py
=======================
Phase 5 sanity check — computes resource requirements and deficits for all
8 areas and prints a table, totals, donor eligibility and validations.

No pytest required — plain print-based verification suitable for a demo.

Usage (from project root):
    .venv\\Scripts\\python.exe backend\\risk\\test_resource_demand.py
    .venv\\Scripts\\python.exe backend\\risk\\test_resource_demand.py --as-of "2024-08-14 20:00:00"

Output is ASCII-only so it never crashes the Windows cp1252 console.
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from backend.risk.resource_demand import (          # noqa: E402
    RESOURCES,
    calculate_deficits,
    calculate_resource_requirements,
    find_deficit_areas,
    find_surplus_areas,
    get_risk_inputs,
    run_resource_demand_engine,
    validate_requirements,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 5 resource demand test")
    parser.add_argument("--as-of", default=None,
                        help='Timestamp, e.g. "2024-08-14 20:00:00".')
    parser.add_argument("--no-forecast", action="store_true",
                        help="Use Phase 3 current risk instead of Phase 4.")
    args = parser.parse_args()

    print("=" * 92)
    print("PHASE 5 - RESOURCE DEMAND AND DEFICIT ENGINE")
    print("=" * 92)

    result = run_resource_demand_engine(
        as_of=args.as_of, prefer_forecast=not args.no_forecast
    )

    print(f"As of        : {result['as_of']}")
    print(f"Risk source  : {result['risk_source']}")
    print("Risk input   : " + ", ".join(
        f"{k}={v:.1f}" for k, v in sorted(result["risk_by_area"].items())
    ))
    print()

    reqs = result["requirements"]

    # ---- Main table: 8 areas x 3 resources ------------------------------
    print(f"{'Area':<11} {'Resource':<14} {'Risk':>6} {'Current':>8} "
          f"{'Required':>9} {'Surplus':>8} {'Deficit':>8}")
    print("-" * 92)
    last_area = None
    for r in reqs:
        if last_area is not None and r.area_id != last_area:
            print()
        last_area = r.area_id
        print(f"{r.area_name:<11} {r.resource:<14} {r.predicted_risk:>6.1f} "
              f"{r.current:>8} {r.required:>9} {r.surplus:>8} {r.deficit:>8}")
    print("-" * 92)
    print()

    # ---- Totals ----------------------------------------------------------
    totals = result["totals"]
    print("TOTALS PER RESOURCE")
    print(f"{'Resource':<14} {'Current':>8} {'Required':>9} {'Surplus':>8} "
          f"{'Deficit':>8} {'Net':>6}")
    print("-" * 60)
    for res in RESOURCES:
        t = totals[res]
        print(f"{res:<14} {t['total_current']:>8} {t['total_required']:>9} "
              f"{t['total_surplus']:>8} {t['total_deficit']:>8} {t['net']:>6}")
    print("-" * 60)
    print()

    # ---- Donor / recipient rule ------------------------------------------
    print("TRANSFER ELIGIBILITY (a deficit area CANNOT donate that resource)")
    for res in RESOURCES:
        donors = find_surplus_areas(reqs, res)
        needs  = find_deficit_areas(reqs, res)
        print(f"  {res:<14} donors={','.join(donors) or '-':<20} "
              f"recipients={','.join(needs) or '-'}")
    print()

    # ---- Formula spot-check ----------------------------------------------
    print("FORMULA SPOT-CHECK (first record)")
    print(f"  {reqs[0].area_name} / {reqs[0].resource}: {reqs[0].breakdown}"
          f" -> required={reqs[0].required}")
    print()

    # ---- Validations ------------------------------------------------------
    errors = result["validation_errors"]
    if errors:
        print("VALIDATION FAILURES:")
        for e in errors:
            print(f"  FAIL  {e}")
        sys.exit(1)

    print("VALIDATIONS PASSED")
    print("  - no negative current quantities")
    print("  - all required quantities >= 0")
    print("  - all deficits >= 0")
    print("  - surplus and deficit never both positive")
    print(f"  - totals conserved for all {len(RESOURCES)} resources "
          f"({len(reqs)} area x resource records)")
    print("  - no deficit area appears in any donor list")
    print()
    print("Done.")


if __name__ == "__main__":
    main()
