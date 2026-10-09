# risk package — explainable current climate risk engine (Phase 3)
#             + resource demand/deficit engine (Phase 5)
from .risk_engine import (
    AreaObservation,
    RiskResult,
    calculate_hazard_score,
    calculate_vulnerability_score,
    calculate_exposure_score,
    calculate_flood_risk,
    classify_risk,
    load_latest_observations,
    run_risk_engine,
)

from .resource_demand import (
    RESOURCES,
    ResourceRequirement,
    calculate_deficits,
    calculate_resource_requirements,
    can_donate,
    find_deficit_areas,
    find_surplus_areas,
    get_risk_inputs,
    run_resource_demand_engine,
    validate_requirements,
)

__all__ = [
    "AreaObservation",
    "RiskResult",
    "calculate_hazard_score",
    "calculate_vulnerability_score",
    "calculate_exposure_score",
    "calculate_flood_risk",
    "classify_risk",
    "load_latest_observations",
    "run_risk_engine",
    "RESOURCES",
    "ResourceRequirement",
    "calculate_deficits",
    "calculate_resource_requirements",
    "can_donate",
    "find_deficit_areas",
    "find_surplus_areas",
    "get_risk_inputs",
    "run_resource_demand_engine",
    "validate_requirements",
]
