"""
resource_demand.py
==================
Phase 5 — Resource Demand and Deficit Engine.

PURPOSE
-------
For every area and every resource type, decide how many units that area
*should* have given its forecast flood risk and its structural exposure, then
compare that against the real inventory in ``resources.csv``:

    current    → what the area physically has
    required   → what the formula says it needs (configurable)
    surplus    → max(0, current - required)   ← eligible for donation
    deficit    → max(0, required - current)   ← needs an inbound transfer

    surplus and deficit can NEVER both be positive (they are complements).

THE RULE THAT MATTERS FOR PHASE 6
---------------------------------
An area that has a deficit in a resource CANNOT donate that resource.
``find_surplus_areas()`` is therefore the only list of eligible donors; it
excludes every area with a deficit by construction.

REQUIREMENT FORMULA
-------------------
    required(area, resource) =
        clamp( ceil( BASE_UNITS[resource]
                     x RISK_MULT(predicted_risk)
                     x EXPOSURE_MULT(population, density)
                     x VULN_MULT(vulnerability_index) ),
               0, MAX_REQUIRED[resource] )

    RISK_MULT(risk)       = 0.50 + 1.00 * risk / 100
                            risk 0   -> 0.50   (readiness floor, never 0)
                            risk 50  -> 1.00   (reference risk)
                            risk 100 -> 1.50

    EXPOSURE_MULT         = 0.80 + 0.40 * population/3500k
                                   + 0.30 * density/3000 per km2
                            range 0.80 - 1.50

    VULN_MULT             = 0.80 + 0.60 * vulnerability_index
                            range 0.80 - 1.40

    BASE_UNITS            pumps 7 · rescue_teams 6 · medical_kits 38
    MAX_REQUIRED          pumps 25 · rescue_teams 20 · medical_kits 120

WHY THESE BASE UNITS: at reference risk (50) this formula reproduces the
static ``*_required`` baseline already stored in resources.csv for all 8 areas
(within roughly +-10%), so the dynamic requirement is anchored to the
dataset's own planning numbers instead of being invented.  The difference is
that ours then moves with the 6-hour forecast.

SYNTHETIC DATA DISCLAIMER: inventory and area statistics are synthetic and
for prototype demonstration only.
"""

from __future__ import annotations

import csv
import math
import os
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR     = os.path.join(_BACKEND_DIR, "data")
RESOURCES_CSV = os.path.join(DATA_DIR, "resources.csv")
AREAS_CSV     = os.path.join(DATA_DIR, "areas.csv")

# ---------------------------------------------------------------------------
# Resource vocabulary
# ---------------------------------------------------------------------------

RESOURCES: List[str] = ["pumps", "rescue_teams", "medical_kits"]

# ---------------------------------------------------------------------------
# Configurable requirement parameters — tune here, not inside the formula
# ---------------------------------------------------------------------------

BASE_UNITS: Dict[str, float] = {
    "pumps":         12.0,   # raised: NE India flood zones need more pumps at baseline
    "rescue_teams":  10.0,   # raised: multi-state monsoon response requires larger teams
    "medical_kits":  60.0,   # raised: higher baseline medical preparedness for remote areas
}

MAX_REQUIRED: Dict[str, int] = {
    "pumps":         35,
    "rescue_teams":  28,
    "medical_kits": 160,
}

# Risk scaling: multiplier = RISK_FLOOR + RISK_GAIN * risk/100
RISK_FLOOR     = 0.50     # multiplier at risk 0  (readiness floor)
RISK_GAIN      = 1.00     # extra multiplier at risk 100
REFERENCE_RISK = 50.0     # risk level at which multiplier == 1.0

# Exposure scaling
EXPO_BASE        = 0.80
EXPO_POP_WEIGHT  = 0.40
EXPO_DENS_WEIGHT = 0.30
POP_NORM_MAX     = 3500.0   # thousands — normalisation ceiling
DENSITY_NORM_MAX = 3000.0   # people per km2 — normalisation ceiling

# Vulnerability scaling
VULN_BASE   = 0.80
VULN_WEIGHT = 0.60


# ---------------------------------------------------------------------------
# Data record
# ---------------------------------------------------------------------------

@dataclass
class ResourceRequirement:
    """One area x one resource: inventory vs computed requirement."""
    area_id:         str
    area_name:       str
    resource:        str
    current:         int
    required:        int
    surplus:         int = 0
    deficit:         int = 0
    predicted_risk:  float = 0.0
    breakdown:       str = ""

    def to_dict(self) -> dict:
        return {
            "area_id":   self.area_id,
            "resource":  self.resource,
            "current":   self.current,
            "required":  self.required,
            "surplus":   self.surplus,
            "deficit":   self.deficit,
            # extras for explainability
            "area_name":       self.area_name,
            "predicted_risk":  round(self.predicted_risk, 2),
            "formula":         self.breakdown,
        }


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

def load_area_static(path: str = AREAS_CSV) -> Dict[str, dict]:
    """Static exposure/vulnerability attributes per area from areas.csv."""
    areas: Dict[str, dict] = {}
    with open(path, newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            areas[row["area_id"]] = {
                "area_name":             row["area_name"],
                "population":            float(row["population_thousands"]),
                "population_density":    float(row["population_density"]),
                "vulnerability_index":   float(row["vulnerability_index"]),
                "road_accessibility":    float(row["road_accessibility"]),
            }
    return areas


def load_inventory(path: str = RESOURCES_CSV) -> Dict[str, dict]:
    """Current quantities per area from resources.csv (plus static baselines)."""
    inventory: Dict[str, dict] = {}
    with open(path, newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            inventory[row["area_id"]] = {
                "area_name":       row["area_name"],
                "current":         {r: int(row[r]) for r in RESOURCES},
                "static_baseline": {
                    r: int(row[f"{r}_required"]) for r in RESOURCES
                },
            }
    return inventory


# ---------------------------------------------------------------------------
# Multipliers (the configurable formula)
# ---------------------------------------------------------------------------

def risk_multiplier(predicted_risk: float) -> float:
    """0.50 at risk 0, 1.00 at reference risk 50, 1.50 at risk 100."""
    risk = min(max(float(predicted_risk), 0.0), 100.0)
    return RISK_FLOOR + RISK_GAIN * (risk / 100.0)


def exposure_multiplier(population: float, population_density: float) -> float:
    """Scales with how many people live there and how densely (0.80 - 1.50)."""
    pop_norm  = min(max(population / POP_NORM_MAX, 0.0), 1.0)
    dens_norm = min(max(population_density / DENSITY_NORM_MAX, 0.0), 1.0)
    return EXPO_BASE + EXPO_POP_WEIGHT * pop_norm + EXPO_DENS_WEIGHT * dens_norm


def vulnerability_multiplier(vulnerability_index: float) -> float:
    """Fragile regions need more help per unit of hazard (0.80 - 1.40)."""
    v = min(max(vulnerability_index, 0.0), 1.0)
    return VULN_BASE + VULN_WEIGHT * v


def calculate_resource_requirements(
    risk_by_area:   Dict[str, float],
    area_static:    Optional[Dict[str, dict]] = None,
    inventory:      Optional[Dict[str, dict]] = None,
    base_units:     Optional[Dict[str, float]] = None,
    max_required:   Optional[Dict[str, int]] = None,
) -> List[ResourceRequirement]:
    """
    Core calculation: current vs required for every area x resource.

    Parameters
    ----------
    risk_by_area : {area_id: predicted flood risk 0-100}
                   (Phase 4 output, or Phase 3 current risk as fallback).
    area_static  : optional override of areas.csv contents.
    inventory    : optional override of resources.csv contents.
    base_units   : optional override of BASE_UNITS (configurability).
    max_required : optional override of MAX_REQUIRED (configurability).

    Returns
    -------
    List of ResourceRequirement (8 areas x 3 resources = 24 records),
    each carrying current, required, surplus and deficit.
    """
    areas     = area_static if area_static is not None else load_area_static()
    inv       = inventory   if inventory   is not None else load_inventory()
    bases     = base_units  if base_units  is not None else BASE_UNITS
    caps      = max_required if max_required is not None else MAX_REQUIRED

    records: List[ResourceRequirement] = []

    for area_id in areas:
        if area_id not in inv:
            raise KeyError(f"resources.csv has no row for area {area_id}")
        if area_id not in risk_by_area:
            raise KeyError(f"No predicted risk supplied for area {area_id}")

        a      = areas[area_id]
        risk   = float(risk_by_area[area_id])
        m_risk = risk_multiplier(risk)
        m_expo = exposure_multiplier(a["population"], a["population_density"])
        m_vuln = vulnerability_multiplier(a["vulnerability_index"])

        for resource in RESOURCES:
            raw      = bases[resource] * m_risk * m_expo * m_vuln
            required = int(math.ceil(raw))
            required = max(0, min(required, caps.get(resource, required)))

            current = int(inv[area_id]["current"][resource])

            surplus = max(0, current - required)
            deficit = max(0, required - current)

            records.append(ResourceRequirement(
                area_id        = area_id,
                area_name      = a["area_name"],
                resource       = resource,
                current        = current,
                required       = required,
                surplus        = surplus,
                deficit        = deficit,
                predicted_risk = risk,
                breakdown      = (
                    f"ceil({bases[resource]:g} x {m_risk:.3f} risk "
                    f"x {m_expo:.3f} exposure x {m_vuln:.3f} vulnerability "
                    f"= {raw:.2f})"
                ),
            ))

    return records


def calculate_deficits(
    requirements: List[ResourceRequirement],
) -> Dict[str, dict]:
    """
    Aggregate the per-area records into per-resource totals.

    Returns
    -------
    {
      "pumps": {
          "total_current": .., "total_required": ..,
          "total_surplus": .., "total_deficit": ..,
          "net": surplus - deficit,
          "deficit_areas": ["MHO", ...],
          "surplus_areas": ["IND", ...],   # eligible donors only
      }, ...
    }
    """
    summary: Dict[str, dict] = {}
    for resource in RESOURCES:
        rows = [r for r in requirements if r.resource == resource]
        total_current  = sum(r.current  for r in rows)
        total_required = sum(r.required for r in rows)
        total_surplus  = sum(r.surplus  for r in rows)
        total_deficit  = sum(r.deficit  for r in rows)
        summary[resource] = {
            "total_current":  total_current,
            "total_required": total_required,
            "total_surplus":  total_surplus,
            "total_deficit":  total_deficit,
            "net":            total_surplus - total_deficit,
            "deficit_areas":  [r.area_id for r in rows if r.deficit > 0],
            "surplus_areas":  [r.area_id for r in rows if r.surplus > 0],
        }
    return summary


def find_deficit_areas(
    requirements: List[ResourceRequirement],
    resource:     str,
) -> List[str]:
    """Area ids that are SHORT on `resource` (they need an inbound transfer)."""
    _check_resource(resource)
    return [r.area_id for r in requirements
            if r.resource == resource and r.deficit > 0]


def find_surplus_areas(
    requirements: List[ResourceRequirement],
    resource:     str,
) -> List[str]:
    """
    Area ids that may DONATE `resource`.

    By construction surplus > 0 implies deficit == 0, so an area that itself
    is short can never appear here — the Phase 6 optimisation rule.
    """
    _check_resource(resource)
    return [r.area_id for r in requirements
            if r.resource == resource and r.surplus > 0 and r.deficit == 0]


def can_donate(requirements: List[ResourceRequirement],
               area_id: str, resource: str) -> bool:
    """True only if the area has spare units AND no deficit of that resource."""
    for r in requirements:
        if r.area_id == area_id and r.resource == resource:
            return r.surplus > 0 and r.deficit == 0
    return False


def _check_resource(resource: str) -> None:
    if resource not in RESOURCES:
        raise ValueError(f"Unknown resource '{resource}'. Choose from {RESOURCES}")


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_requirements(requirements: List[ResourceRequirement]) -> List[str]:
    """
    Check the five invariants of this phase. Returns a list of error strings
    (empty list = all checks passed).
    """
    errors: List[str] = []
    expected = len(load_area_static()) * len(RESOURCES)
    if len(requirements) != expected:
        errors.append(f"expected {expected} records, got {len(requirements)}")

    for r in requirements:
        if r.current < 0:
            errors.append(f"{r.area_id}/{r.resource}: negative current {r.current}")
        if r.required < 0:
            errors.append(f"{r.area_id}/{r.resource}: negative required {r.required}")
        if r.surplus < 0 or r.deficit < 0:
            errors.append(f"{r.area_id}/{r.resource}: negative surplus/deficit")
        if r.surplus > 0 and r.deficit > 0:
            errors.append(f"{r.area_id}/{r.resource}: surplus AND deficit both > 0")
        if r.surplus != max(0, r.current - r.required):
            errors.append(f"{r.area_id}/{r.resource}: surplus inconsistent")
        if r.deficit != max(0, r.required - r.current):
            errors.append(f"{r.area_id}/{r.resource}: deficit inconsistent")

    # Conservation: every unit in resources.csv is represented exactly once,
    # and  surplus - deficit == current - required  for each resource.
    inv = load_inventory()
    for resource in RESOURCES:
        csv_total = sum(inv[a]["current"][resource] for a in inv)
        got_total = sum(r.current for r in requirements if r.resource == resource)
        if csv_total != got_total:
            errors.append(
                f"{resource}: inventory not conserved "
                f"(csv={csv_total}, computed={got_total})"
            )
        net = sum(r.surplus - r.deficit for r in requirements
                  if r.resource == resource)
        diff = sum(r.current - r.required for r in requirements
                   if r.resource == resource)
        if net != diff:
            errors.append(f"{resource}: conservation identity failed")

    # Donor rule: nobody with a deficit may appear as a donor.
    for resource in RESOURCES:
        donors = set(find_surplus_areas(requirements, resource))
        short  = set(find_deficit_areas(requirements, resource))
        if donors & short:
            errors.append(f"{resource}: deficit area(s) listed as donors: {donors & short}")

    return errors


# ---------------------------------------------------------------------------
# Risk input: Phase 4 forecast, with Phase 3 fallback
# ---------------------------------------------------------------------------

def get_risk_inputs(
    as_of: Optional[str] = None,
    prefer_forecast: bool = True,
) -> Tuple[Dict[str, float], str]:
    """
    Build {area_id: risk} for the demand formula.

    Preference order:
      1. Phase 4 ML forecast (predicted risk 6h ahead) — if the model exists.
      2. Phase 3 rule-based current risk — fallback so the engine still runs.

    Returns (risk_by_area, source_label).
    """
    if prefer_forecast:
        try:
            from backend.forecasting.predict import predict_forecast
            results = predict_forecast(as_of=as_of)
            return (
                {r["area_id"]: float(r["predicted_risk"]) for r in results},
                "Phase 4 RandomForest forecast (6h ahead)",
            )
        except FileNotFoundError:
            reason = "Phase 4 model not trained yet"
    else:
        reason = "forecast disabled by caller"

    from backend.risk import run_risk_engine
    results = run_risk_engine(as_of=as_of)
    return (
        {r.area_id: float(r.risk_score) for r in results},
        f"Phase 3 rule-based current risk ({reason})",
    )


# ---------------------------------------------------------------------------
# End-to-end entry point (mirrors run_risk_engine)
# ---------------------------------------------------------------------------

def run_resource_demand_engine(
    as_of:         Optional[str] = None,
    risk_by_area:  Optional[Dict[str, float]] = None,
    prefer_forecast: bool = True,
) -> Dict:
    """
    One call that produces everything Phase 6 will need:
    per-area records, per-resource totals, donor/recipient lists, validations.

    Pass `risk_by_area` explicitly to reuse a risk set the caller already has
    (e.g. a FastAPI request) instead of recomputing it.
    """
    source = "caller-supplied"
    if risk_by_area is None:
        risk_by_area, source = get_risk_inputs(
            as_of=as_of, prefer_forecast=prefer_forecast
        )

    requirements = calculate_resource_requirements(risk_by_area)
    totals       = calculate_deficits(requirements)
    errors       = validate_requirements(requirements)

    return {
        "as_of":        str(as_of) if as_of else "latest available data",
        "risk_source":  source,
        "risk_by_area": risk_by_area,
        "requirements": requirements,
        "totals":       totals,
        "validation_errors": errors,
        "ok":           not errors,
    }
