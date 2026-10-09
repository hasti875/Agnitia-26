"""
test_risk_engine.py
===================
Quick sanity-check for the risk engine.
Prints a formatted table of current flood risk for all 8 regions.

Usage (from project root):
    .venv\\Scripts\\python.exe backend/risk/test_risk_engine.py

No pytest required — plain print-based verification suitable for a demo.
"""

import sys
import os

# Allow running from project root without installing the package
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from risk.risk_engine import run_risk_engine, HAZARD_WEIGHTS, VULNERABILITY_WEIGHTS, EXPOSURE_WEIGHTS

LEVEL_COLOURS = {
    "LOW":       "\033[92m",   # green
    "MODERATE":  "\033[93m",   # yellow
    "HIGH":      "\033[91m",   # red
    "VERY HIGH": "\033[35m",   # magenta
    "CRITICAL":  "\033[41m",   # red background
}
RESET = "\033[0m"


def colour(level: str, text: str) -> str:
    return f"{LEVEL_COLOURS.get(level, '')}{text}{RESET}"


def print_weights():
    print("  HAZARD weights:")
    for k, v in HAZARD_WEIGHTS.items():
        print(f"    {k:<25} {v:.2f}")
    print("  VULNERABILITY weights:")
    for k, v in VULNERABILITY_WEIGHTS.items():
        print(f"    {k:<25} {v:.2f}")
    print("  EXPOSURE weights:")
    for k, v in EXPOSURE_WEIGHTS.items():
        print(f"    {k:<25} {v:.2f}")


def main():
    print("=" * 80)
    print("  CLIMATE RISK ARBITRAGE ENGINE — Current Risk Assessment")
    print("=" * 80)
    print()
    print("Weight configuration:")
    print_weights()
    print()

    results = run_risk_engine()

    if not results:
        print("ERROR: No results returned.  Check that climate_history.csv exists.")
        sys.exit(1)

    print(f"Assessment timestamp: {results[0].timestamp}")
    print()

    # ── Summary table ──────────────────────────────────────────────────────
    header = (
        f"{'#':<3} {'Area':<12} {'Score':>6} {'Level':<10} "
        f"{'Hazard':>8} {'Vuln':>6} {'Expsr':>6} "
        f"{'Rain':>6} {'6h-Rain':>8} {'River':>7} {'Trend':>7}"
    )
    print(header)
    print("-" * 80)

    for i, r in enumerate(results, 1):
        trend_sign = "↑" if r.river_trend_3h > 0.05 else ("↓" if r.river_trend_3h < -0.05 else "→")
        level_str  = colour(r.risk_level, f"{r.risk_level:<10}")

        print(
            f"{i:<3} {r.area_name:<12} "
            f"{r.risk_score:>6.1f} {level_str} "
            f"{r.hazard_score:>8.4f} {r.vulnerability_score:>6.4f} {r.exposure_score:>6.4f} "
            f"{r.rainfall_mm:>6.2f} {r.cumulative_rain_6h:>8.2f} "
            f"{r.river_level_m:>7.3f} "
            f"{r.river_trend_3h:>+6.3f}{trend_sign}"
        )

    print("-" * 80)
    print()

    # ── Detailed breakdown ─────────────────────────────────────────────────
    print("Detailed breakdown:")
    print()
    for r in results:
        print(f"  [{r.area_id}] {r.area_name}")
        print(f"    Risk score  : {r.risk_score:.1f} / 100  ({r.risk_level})")
        print(f"    Hazard      : {r.hazard_score:.4f}  "
              f"(rain={r.recent_rainfall_score:.3f}, "
              f"6h-rain={r.cumulative_rain_score:.3f}, "
              f"river-level={r.river_level_score:.3f}, "
              f"trend={r.river_trend_score:.3f})")
        print(f"    Vulnerability: {r.vulnerability_score:.4f}  "
              f"Exposure: {r.exposure_score:.4f}")
        print(f"    Key factors : {r.key_factors}")
        print()

    # ── Validation assertions ──────────────────────────────────────────────
    print("Running assertions ...")
    errors = []

    area_ids_found = {r.area_id for r in results}
    expected_ids   = {"IND", "UJJ", "DEW", "DHA", "RAT", "MAN", "MHO", "SEH"}
    missing = expected_ids - area_ids_found
    if missing:
        errors.append(f"Missing regions: {missing}")

    for r in results:
        if not (0.0 <= r.risk_score <= 100.0):
            errors.append(f"{r.area_id}: risk_score {r.risk_score} out of [0,100]")
        if not (0.0 <= r.hazard_score <= 1.0):
            errors.append(f"{r.area_id}: hazard_score {r.hazard_score} out of [0,1]")
        if r.risk_level not in {"LOW", "MODERATE", "HIGH", "VERY HIGH", "CRITICAL"}:
            errors.append(f"{r.area_id}: unknown risk_level '{r.risk_level}'")
        if not r.key_factors:
            errors.append(f"{r.area_id}: key_factors is empty")

    if errors:
        print("ASSERTION FAILURES:")
        for e in errors:
            print(f"  ✗ {e}")
        sys.exit(1)
    else:
        print(f"  All assertions passed ✓  ({len(results)} regions assessed)")

    print()
    print("Done.")


if __name__ == "__main__":
    main()
