"""
rule_based_calculator.py
========================
Separate, testable rule-based flood risk calculation utility for Climate Risk Engine.

Combines observed rainfall (past 24h/6h), upcoming forecast rainfall (next 6h),
precipitation probability, soil moisture, and static area vulnerability.

Thresholds:
- LOW: Score < 30
- MODERATE: 30 <= Score < 60
- HIGH: 60 <= Score < 80
- VERY HIGH: Score >= 80

Provides transparent, step-by-step risk score calculation explanations.
Explicitly labeled as a rule-based prototype estimate until a trained ML model is integrated.
"""

from __future__ import annotations
from typing import Dict, Any, Tuple, Optional

# Default Configurable Risk Category Thresholds
DEFAULT_THRESHOLDS = {
    "LOW_MAX": 30.0,
    "MODERATE_MAX": 60.0,
    "HIGH_MAX": 80.0,
    # Anything >= 80.0 is VERY HIGH
}

METHODOLOGY_DISCLAIMER = (
    "Rule-Based Risk Estimate (Uncalibrated Prototype). "
    "Calculated dynamically from Open-Meteo observed rainfall, 6h forecast, soil moisture, and static vulnerability index."
)


def categorize_risk_score(score: float, thresholds: Optional[Dict[str, float]] = None) -> str:
    """Categorize numerical risk score (0-100) into Low, Moderate, High, or Very High."""
    t = thresholds or DEFAULT_THRESHOLDS
    val = float(score)
    if val < t.get("LOW_MAX", 30.0):
        return "LOW"
    elif val < t.get("MODERATE_MAX", 60.0):
        return "MODERATE"
    elif val < t.get("HIGH_MAX", 80.0):
        return "HIGH"
    else:
        return "VERY HIGH"


def calculate_rule_based_risk(
    observed_rain_24h_mm: float = 0.0,
    forecast_rain_6h_mm: float = 0.0,
    precip_probability_pct: float = 0.0,
    soil_moisture: float = 0.0,
    vulnerability_index: float = 0.5,
    thresholds: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """
    Calculate deterministic, testable rule-based risk score (0-100).

    Formula Components:
    1. Rainfall Index (0-50 pts): 40% observed 24h rain + 60% forecast 6h rain (capped at 50)
    2. Soil Saturation Factor (1.0 - 1.3x): Amplifies runoff if soil moisture is high
    3. Probability Multiplier (0.8 - 1.2x): Scales forecast confidence
    4. Vulnerability Multiplier (1.0 - 1.5x): Scales by historical flood frequency & population density
    """
    # Sanitize inputs
    obs = max(0.0, float(observed_rain_24h_mm or 0.0))
    fc = max(0.0, float(forecast_rain_6h_mm or 0.0))
    prob = max(0.0, min(100.0, float(precip_probability_pct or 0.0)))
    soil = max(0.0, min(1.0, float(soil_moisture or 0.0)))
    vuln = max(0.0, min(1.0, float(vulnerability_index or 0.5)))

    # 1. Base Rainfall Weight
    rainfall_metric = (obs * 0.4) + (fc * 0.6)
    rainfall_index = min(50.0, rainfall_metric * 1.5)

    # 2. Soil Saturation Factor
    soil_factor = 1.0 + (soil * 0.3)

    # 3. Probability Weight
    prob_factor = 0.8 + (prob / 100.0) * 0.4

    # 4. Vulnerability Multiplier
    vuln_factor = 1.0 + (vuln * 0.5)

    # Raw Score Calculation
    raw_score = rainfall_index * soil_factor * prob_factor * vuln_factor

    # Final Risk Index bounded [0.0, 100.0]
    final_score = round(min(100.0, max(0.0, raw_score)), 1)
    risk_level = categorize_risk_score(final_score, thresholds)

    # Step-by-step human readable explanation
    explanation = (
        f"Rule-Based Calculation Breakdown: Observed Rain (24h)={obs}mm, Forecast Rain (6h)={fc}mm "
        f"-> Rainfall Index={rainfall_index:.1f}/50; Soil Factor={soil_factor:.2f}x; "
        f"Precip Prob={prob}% ({prob_factor:.2f}x); Vulnerability={vuln:.2f} ({vuln_factor:.2f}x). "
        f"Final Risk Index={final_score}/100 [{risk_level}]."
    )

    return {
        "predicted_risk": final_score,
        "risk_level": risk_level,
        "methodology": METHODOLOGY_DISCLAIMER,
        "explanation": explanation,
        "components": {
            "observed_rain_24h_mm": obs,
            "forecast_rain_6h_mm": fc,
            "precip_probability_pct": prob,
            "soil_moisture": soil,
            "vulnerability_index": vuln,
            "rainfall_index": round(rainfall_index, 2),
            "soil_factor": round(soil_factor, 2),
            "prob_factor": round(prob_factor, 2),
            "vuln_factor": round(vuln_factor, 2),
        }
    }
