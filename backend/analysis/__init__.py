# analysis package — fixed vs optimised comparator (Phase 9)
from .comparison import (
    METRIC_NAME,
    EXPOSURE_POP_WEIGHT,
    EXPOSURE_DENSITY_WEIGHT,
    EXPOSURE_BASE,
    EXPOSURE_GAIN,
    SHORTAGE_GAIN,
    POP_NORM_MAX,
    DENSITY_NORM_MAX,
    AreaInventory,
    exposure_factor,
    shortage_factor,
    area_impact,
    compare_allocations,
)

__all__ = [
    "METRIC_NAME",
    "EXPOSURE_POP_WEIGHT",
    "EXPOSURE_DENSITY_WEIGHT",
    "EXPOSURE_BASE",
    "EXPOSURE_GAIN",
    "SHORTAGE_GAIN",
    "POP_NORM_MAX",
    "DENSITY_NORM_MAX",
    "AreaInventory",
    "exposure_factor",
    "shortage_factor",
    "area_impact",
    "compare_allocations",
]
