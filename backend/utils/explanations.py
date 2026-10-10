"""
explanations.py
===============
Phase 10 — Human-Readable Explanation Engine.

PURPOSE
-------
Turn the *existing* engine outputs (Phase 3 risk, Phase 5 resource demand,
Phase 6 optimizer, Phase 7 scenarios, Phase 9 comparison) into short,
plain-English explanations suitable for a disaster-response decision-support
demo.

DESIGN RULES
------------
* Reuse existing functions and data structures.  No parallel risk engine,
  optimizer or metric is re-implemented here.
* Explain only facts that are present in the supplied input data / computed
  outputs.  If a needed field is missing, return an explicit ``limitation``
  instead of guessing.
* Distinguish model *predictions* ("predicted risk") from observed *facts*
  and optimizer *recommendations* ("recommended transfer").
* Never claim that resources save lives, guarantee prevention, or establish
  real-world disaster reduction.
* Deterministic for identical inputs (pure string templating, no randomness,
  no wall-clock time).

DISCLAIMER
----------
All explanations describe a PROTOTYPE decision-support system built on
SYNTHETIC data.  They are estimates for demonstration only and do NOT
establish actual real-world disaster reduction.
"""

from __future__ import annotations

from typing import Dict, List, Optional

# ---------------------------------------------------------------------------
# Reuse existing engines (no re-implementation)
# ---------------------------------------------------------------------------
from backend.risk import classify_risk
from backend.risk.resource_demand import RESOURCES

DISCLAIMER = (
    "Decision-support system powered by live Open-Meteo weather telemetry and "
    "real-world area data for the Seven Sister States of Northeast India. "
    "Risk scores are rule-based estimates and do NOT constitute official "
    "disaster forecasts or guaranteed prevention outcomes."
)

# Human-friendly resource labels (kept consistent with the RESOURCES ids).
_RESOURCE_LABEL = {
    "pumps": "pumps",
    "rescue_teams": "rescue teams",
    "medical_kits": "medical kits",
}


def _label(resource: str) -> str:
    return _RESOURCE_LABEL.get(resource, resource)


def _num(value, nd: int = 1) -> str:
    """Format a number, tolerating None / non-numeric input."""
    try:
        return f"{float(value):.{nd}f}"
    except (TypeError, ValueError):
        return "n/a"


# ===========================================================================
# 1. Area risk
# ===========================================================================

def explain_area_risk(risk_result: dict) -> dict:
    """
    Explain one area's predicted risk score and category.

    Accepts either a Phase 3 ``RiskResult.to_dict()`` mapping or a Phase 4
    forecast row.  Uses only fields that are actually present.

    Returns
    -------
    {
      "type": "area_risk",
      "area_id": str,
      "area_name": str,
      "predicted_risk": float | None,
      "risk_level": str | None,
      "explanation": str,
      "limitation": str | None,
    }
    """
    if not isinstance(risk_result, dict):
        return {
            "type": "area_risk",
            "area_id": None,
            "area_name": None,
            "predicted_risk": None,
            "risk_level": None,
            "explanation": "No risk data supplied; cannot explain this area.",
            "limitation": "Missing or malformed risk input.",
        }

    area_id = risk_result.get("area_id")
    area_name = risk_result.get("area_name") or area_id or "Unknown area"

    # Predicted / current risk score (accept several key names).
    score = risk_result.get("predicted_risk")
    if score is None:
        score = risk_result.get("risk_score")
    score = _to_float(score)

    level = risk_result.get("risk_level") or risk_result.get(
        "predicted_risk_level"
    )
    if level is None and score is not None:
        level = classify_risk(score)

    if score is None:
        return {
            "type": "area_risk",
            "area_id": area_id,
            "area_name": area_name,
            "predicted_risk": None,
            "risk_level": None,
            "explanation": (
                f"No numeric risk score is available for {area_name}, so the "
                "predicted risk cannot be described."
            ),
            "limitation": "Missing 'predicted_risk' / 'risk_score' field.",
        }

    parts = [
        f"{area_name} has a predicted flood risk of {_num(score)} out of 100, "
        f"classified as {level}."
    ]

    # Phase 3 sub-scores, if present (hazard / vulnerability / exposure).
    hazard = _to_float(risk_result.get("hazard_score"))
    vuln = _to_float(risk_result.get("vulnerability_score"))
    expo = _to_float(risk_result.get("exposure_score"))
    if hazard is not None and vuln is not None and expo is not None:
        parts.append(
            "This combines a hazard score of "
            f"{_num(hazard, 2)}, vulnerability of {_num(vuln, 2)} and "
            f"exposure of {_num(expo, 2)}."
        )

    # Key factors produced by the Phase 3 engine (verbatim, already factual).
    key_factors = risk_result.get("key_factors")
    if isinstance(key_factors, str) and key_factors.strip():
        parts.append(f"Main drivers: {key_factors}")

    # Raw observed inputs, if present (these are observations, not predictions).
    if "rainfall_mm" in risk_result:
        parts.append(
            "Latest observed inputs: "
            f"{_num(risk_result.get('rainfall_mm'))} mm rainfall in the last "
            f"hour, {_num(risk_result.get('cumulative_rain_6h'))} mm over 6 "
            f"hours, river level {_num(risk_result.get('river_level_m'), 2)} m."
        )

    return {
        "type": "area_risk",
        "area_id": area_id,
        "area_name": area_name,
        "predicted_risk": score,
        "risk_level": level,
        "explanation": " ".join(parts),
        "limitation": None,
    }


# ===========================================================================
# 2. Resource shortages
# ===========================================================================

def explain_resource_shortages(requirements: List[dict]) -> dict:
    """
    Explain which resources are deficient for each area, with sizes and the
    current/required values.

    Parameters
    ----------
    requirements : list of Phase 5 ``ResourceRequirement.to_dict()`` mappings
                   (each with area_id, area_name, resource, current, required,
                   deficit, surplus, predicted_risk).

    Returns
    -------
    {
      "type": "resource_shortages",
      "summary": str,
      "areas": [ {area_id, area_name, shortages:[...], explanation} ],
      "limitation": str | None,
    }
    """
    if not isinstance(requirements, list) or not requirements:
        return {
            "type": "resource_shortages",
            "summary": "No resource requirement data supplied.",
            "areas": [],
            "limitation": "Missing or empty 'requirements' input.",
        }

    # Group by area, preserving first-seen order of area ids.
    by_area: Dict[str, dict] = {}
    order: List[str] = []
    for r in requirements:
        if not isinstance(r, dict):
            continue
        aid = r.get("area_id")
        if aid is None:
            continue
        if aid not in by_area:
            by_area[aid] = {
                "area_id": aid,
                "area_name": r.get("area_name") or aid,
                "shortages": [],
            }
            order.append(aid)

    total_deficit_units = 0
    for aid in order:
        entry = by_area[aid]
        for r in requirements:
            if not isinstance(r, dict) or r.get("area_id") != aid:
                continue
            deficit = _to_int(r.get("deficit"))
            if deficit is None or deficit <= 0:
                continue
            resource = r.get("resource", "resource")
            current = _to_int(r.get("current"))
            required = _to_int(r.get("required"))
            total_deficit_units += deficit
            entry["shortages"].append({
                "resource": resource,
                "deficit": deficit,
                "current": current,
                "required": required,
            })

        if entry["shortages"]:
            bits = []
            for s in entry["shortages"]:
                bits.append(
                    f"{s['deficit']} short on {_label(s['resource'])} "
                    f"(has {s['current']}, needs {s['required']})"
                )
            entry["explanation"] = (
                f"{entry['area_name']} is " + " and ".join(bits) + "."
            )
        else:
            entry["explanation"] = (
                f"{entry['area_name']} has no resource deficits in the "
                "current requirement calculation."
            )

    areas_out = [by_area[aid] for aid in order]
    areas_with = [a for a in areas_out if a["shortages"]]

    if total_deficit_units == 0:
        summary = (
            "No resource deficits are currently calculated for any area."
        )
    else:
        summary = (
            f"{len(areas_with)} of {len(areas_out)} areas have at least one "
            f"resource deficit, totalling {total_deficit_units} units across "
            f"{len(RESOURCES)} resource types."
        )

    return {
        "type": "resource_shortages",
        "summary": summary,
        "areas": areas_out,
        "limitation": None,
    }


# ===========================================================================
# 3. Transfer recommendations
# ===========================================================================

def explain_transfer(movement: dict) -> dict:
    """
    Explain why one recommended donor->recipient movement is feasible and
    useful, using the risk / shortage / distance information carried by the
    Phase 6 ``Movement`` (or its dict form).

    Returns
    -------
    {
      "type": "transfer",
      "resource": str,
      "from_area": str,
      "to_area": str,
      "quantity": int | None,
      "explanation": str,
      "limitation": str | None,
    }
    """
    if not isinstance(movement, dict):
        return {
            "type": "transfer",
            "resource": None,
            "from_area": None,
            "to_area": None,
            "quantity": None,
            "explanation": "No movement data supplied; cannot explain a transfer.",
            "limitation": "Missing or malformed movement input.",
        }

    resource = movement.get("resource")
    from_area = movement.get("from_area")
    to_area = movement.get("to_area")
    quantity = _to_int(movement.get("quantity"))

    missing = [
        name for name, val in (
            ("resource", resource),
            ("from_area", from_area),
            ("to_area", to_area),
            ("quantity", quantity),
        ) if val in (None, "")
    ]
    if missing:
        return {
            "type": "transfer",
            "resource": resource,
            "from_area": from_area,
            "to_area": to_area,
            "quantity": quantity,
            "explanation": (
                "Cannot fully explain this transfer because the following "
                f"fields are missing: {', '.join(missing)}."
            ),
            "limitation": f"Missing fields: {', '.join(missing)}.",
        }

    if quantity <= 0:
        return {
            "type": "transfer",
            "resource": resource,
            "from_area": from_area,
            "to_area": to_area,
            "quantity": quantity,
            "explanation": (
                f"The recommended transfer of {quantity} {_label(resource)} "
                f"from {from_area} to {to_area} is not a positive quantity, so "
                "it should not be applied."
            ),
            "limitation": "Non-positive transfer quantity.",
        }

    parts = [
        f"Recommended transfer: move {quantity} {_label(resource)} from "
        f"{from_area} to {to_area}."
    ]

    distance = _to_float(movement.get("distance", movement.get("distance_km")))
    if distance is not None:
        parts.append(f"The route is about {_num(distance, 0)} km.")

    cost = _to_float(movement.get("movement_cost"))
    if cost is not None:
        parts.append(f"The estimated movement cost is {_num(cost, 2)}.")

    # The Phase 6 engine already writes a factual `reason` string.
    reason = movement.get("reason")
    if isinstance(reason, str) and reason.strip():
        parts.append(f"Rationale: {reason}")

    return {
        "type": "transfer",
        "resource": resource,
        "from_area": from_area,
        "to_area": to_area,
        "quantity": quantity,
        "explanation": " ".join(parts),
        "limitation": None,
    }


# ===========================================================================
# 4. Allocation comparison
# ===========================================================================

def explain_allocation_comparison(comparison: dict) -> dict:
    """
    Explain why the optimized allocation's Estimated Prototype Risk-Impact
    Metric differs from the fixed allocation, listing areas that improved and
    areas that worsened.

    Parameters
    ----------
    comparison : the dict returned by Phase 9 ``compare_allocations()``.

    Returns
    -------
    {
      "type": "allocation_comparison",
      "metric_name": str,
      "fixed_risk_impact": float,
      "optimized_risk_impact": float,
      "percentage_reduction": float,
      "improved_areas": [str],
      "worsened_areas": [str],
      "explanation": str,
      "limitation": str | None,
    }
    """
    if not isinstance(comparison, dict):
        return {
            "type": "allocation_comparison",
            "metric_name": None,
            "fixed_risk_impact": None,
            "optimized_risk_impact": None,
            "percentage_reduction": None,
            "improved_areas": [],
            "worsened_areas": [],
            "explanation": "No comparison data supplied; cannot explain it.",
            "limitation": "Missing or malformed comparison input.",
        }

    fixed = _to_float(comparison.get("fixed_risk_impact"))
    optimized = _to_float(comparison.get("optimized_risk_impact"))
    pct = _to_float(comparison.get("percentage_reduction"))
    metric_name = comparison.get("metric_name", "estimated risk-impact metric")

    if fixed is None or optimized is None:
        return {
            "type": "allocation_comparison",
            "metric_name": metric_name,
            "fixed_risk_impact": fixed,
            "optimized_risk_impact": optimized,
            "percentage_reduction": pct,
            "improved_areas": [],
            "worsened_areas": [],
            "explanation": (
                "The comparison is missing its fixed or optimized impact "
                "value, so the difference cannot be explained."
            ),
            "limitation": "Missing 'fixed_risk_impact' or 'optimized_risk_impact'.",
        }

    # Per-area improved / worsened (impact_change < 0 means lower impact = better).
    improved: List[str] = []
    worsened: List[str] = []
    for a in comparison.get("area_results", []) or []:
        if not isinstance(a, dict):
            continue
        change = _to_float(a.get("impact_change"))
        name = a.get("area_name") or a.get("area_id") or "area"
        if change is None:
            continue
        if change < 0:
            improved.append(name)
        elif change > 0:
            worsened.append(name)

    if optimized < fixed:
        direction = (
            f"lower (from {_num(fixed, 4)} to {_num(optimized, 4)})"
        )
        if pct is not None:
            direction += f", a {_num(pct, 2)}% reduction"
        headline = (
            f"Under the {metric_name}, the optimized allocation scores "
            f"{direction} compared with the fixed allocation."
        )
    elif optimized > fixed:
        headline = (
            f"Under the {metric_name}, the optimized allocation scores higher "
            f"({_num(optimized, 4)} vs {_num(fixed, 4)}) than the fixed "
            "allocation, i.e. it does not improve the estimated impact under "
            "this metric."
        )
    else:
        headline = (
            f"Under the {metric_name}, the optimized and fixed allocations "
            f"score the same ({_num(fixed, 4)})."
        )

    parts = [headline]

    if improved:
        parts.append(
            "Areas whose estimated impact decreased: "
            + ", ".join(improved) + "."
        )
    if worsened:
        parts.append(
            "Areas whose estimated impact increased: "
            + ", ".join(worsened) + "."
        )
    if not improved and not worsened:
        parts.append("No individual area's estimated impact changed.")

    # Reuse the Phase 9 assumptions/limitations verbatim where present.
    assumptions = comparison.get("assumptions")
    if isinstance(assumptions, list) and assumptions:
        parts.append("Key assumption: " + assumptions[0])

    return {
        "type": "allocation_comparison",
        "metric_name": metric_name,
        "fixed_risk_impact": fixed,
        "optimized_risk_impact": optimized,
        "percentage_reduction": pct,
        "improved_areas": improved,
        "worsened_areas": worsened,
        "explanation": " ".join(parts),
        "limitation": None,
    }


# ===========================================================================
# 5. What-if scenarios
# ===========================================================================

def explain_scenario(scenario: dict) -> dict:
    """
    Summarise how a Phase 7 what-if scenario changed risks, deficits and
    recommendations relative to the baseline, using only fields present in the
    ``run_scenario()`` output.

    Returns
    -------
    {
      "type": "scenario",
      "scenario": dict,
      "explanation": str,
      "risk_highlights": [str],
      "deficit_highlights": [str],
      "recommendation_highlights": [str],
      "limitation": str | None,
    }
    """
    if not isinstance(scenario, dict):
        return {
            "type": "scenario",
            "scenario": None,
            "explanation": "No scenario data supplied; cannot explain it.",
            "risk_highlights": [],
            "deficit_highlights": [],
            "recommendation_highlights": [],
            "limitation": "Missing or malformed scenario input.",
        }

    scen = scenario.get("scenario") or {}
    parts: List[str] = []

    # Describe the scenario perturbation.
    rain = scen.get("rainfall_change_pct")
    river = scen.get("river_level_change_pct")
    res = scen.get("resource_availability_change_pct")
    if rain in (0, None) and river in (0, None) and res in (0, None):
        parts.append("This is the baseline scenario (no perturbation).")
    else:
        bits = []
        if rain:
            bits.append(f"rainfall {'+' if rain > 0 else ''}{rain}%")
        if river:
            bits.append(f"river level {'+' if river > 0 else ''}{river}%")
        if res:
            bits.append(f"resource availability {'+' if res > 0 else ''}{res}%")
        parts.append("Scenario perturbation: " + ", ".join(bits) + ".")

    # --- Risk changes -------------------------------------------------------
    risk_highlights: List[str] = []
    risk_changes = scenario.get("risk_changes") or []
    for c in risk_changes:
        if not isinstance(c, dict):
            continue
        change = _to_float(c.get("risk_change"))
        if change is None or abs(change) < 0.05:
            continue
        name = c.get("area_name") or c.get("area_id") or "area"
        word = "rises" if change > 0 else "falls"
        risk_highlights.append(
            f"{name} predicted risk {word} by {_num(abs(change))} "
            f"(to {_num(c.get('scenario_predicted_risk'))})."
        )
    # Keep the most notable (largest absolute change), max 3.
    risk_highlights = risk_highlights[:3]
    if risk_highlights:
        parts.append("Risk: " + " ".join(risk_highlights))

    # --- Deficit changes ----------------------------------------------------
    deficit_highlights: List[str] = []
    resource_changes = scenario.get("resource_changes") or []
    for rc in resource_changes:
        if not isinstance(rc, dict):
            continue
        dchange = _to_int(rc.get("deficit_change"))
        if dchange is None or dchange == 0:
            continue
        name = rc.get("area_name") or rc.get("area_id") or "area"
        resource = rc.get("resource", "resource")
        if dchange > 0:
            deficit_highlights.append(
                f"{name} deficit in {_label(resource)} grows by {dchange}."
            )
        else:
            deficit_highlights.append(
                f"{name} deficit in {_label(resource)} shrinks by "
                f"{abs(dchange)}."
            )
    deficit_highlights = deficit_highlights[:3]
    if deficit_highlights:
        parts.append("Deficits: " + " ".join(deficit_highlights))

    # --- Recommendation changes --------------------------------------------
    rec_highlights: List[str] = []
    rec_changes = scenario.get("recommendation_changes") or {}
    if isinstance(rec_changes, dict):
        added = rec_changes.get("added_movements") or []
        removed = rec_changes.get("removed_movements") or []
        changed = rec_changes.get("changed_movements") or []
        if added:
            first = added[0]
            rec_highlights.append(
                f"{len(added)} new transfer(s) recommended, e.g. "
                f"{first.get('quantity')} {_label(first.get('resource'))} "
                f"to {first.get('to_area')}."
            )
        if removed:
            rec_highlights.append(f"{len(removed)} transfer(s) no longer needed.")
        if changed:
            rec_highlights.append(f"{len(changed)} transfer quantity(ies) changed.")
        base_total = rec_changes.get("baseline_total_movements")
        scen_total = rec_changes.get("scenario_total_movements")
        if base_total is not None and scen_total is not None:
            rec_highlights.append(
                f"Total recommended movements go from {base_total} to "
                f"{scen_total}."
            )
    if rec_highlights:
        parts.append("Recommendations: " + " ".join(rec_highlights))

    if len(parts) == 1:
        parts.append("No notable changes to risk, deficits or recommendations.")

    return {
        "type": "scenario",
        "scenario": scen,
        "explanation": " ".join(parts),
        "risk_highlights": risk_highlights,
        "deficit_highlights": deficit_highlights,
        "recommendation_highlights": rec_highlights,
        "limitation": None,
    }


# ===========================================================================
# Aggregate builder (used by the API)
# ===========================================================================

def build_explanations(
    risk_results: Optional[List[dict]] = None,
    requirements: Optional[List[dict]] = None,
    movements: Optional[List[dict]] = None,
    comparison: Optional[dict] = None,
    scenario: Optional[dict] = None,
) -> dict:
    """
    Build a structured set of explanations from existing engine outputs.

    Any argument may be None; the corresponding explanation section is then
    omitted (or carries a limitation if it was expected but empty).
    Deterministic for identical inputs.
    """
    out: Dict[str, object] = {
        "disclaimer": DISCLAIMER,
    }

    if risk_results is not None:
        out["area_risk"] = [
            explain_area_risk(r) for r in risk_results
        ]

    if requirements is not None:
        out["resource_shortages"] = explain_resource_shortages(requirements)

    if movements is not None:
        out["transfers"] = [explain_transfer(m) for m in movements]

    if comparison is not None:
        out["allocation_comparison"] = explain_allocation_comparison(comparison)

    if scenario is not None:
        out["scenario"] = explain_scenario(scenario)

    return out


# ---------------------------------------------------------------------------
# Small coercion helpers (defensive, deterministic)
# ---------------------------------------------------------------------------

def _to_float(value) -> Optional[float]:
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if f != f or f in (float("inf"), float("-inf")):  # NaN / inf guard
        return None
    return f


def _to_int(value) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
