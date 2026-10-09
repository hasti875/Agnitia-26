"""
test_rule_based_calculator.py
==============================
Unit tests for rule-based risk calculation utility.
"""

import os
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.dirname(_HERE)
_PROJECT_ROOT = os.path.dirname(_BACKEND_DIR)

for p in [_PROJECT_ROOT, _BACKEND_DIR]:
    if p not in sys.path:
        sys.path.insert(0, p)

try:
    from backend.risk.rule_based_calculator import (
        calculate_rule_based_risk,
        categorize_risk_score,
        DEFAULT_THRESHOLDS,
    )
except ImportError:
    from risk.rule_based_calculator import (
        calculate_rule_based_risk,
        categorize_risk_score,
        DEFAULT_THRESHOLDS,
    )


class TestRuleBasedCalculator(unittest.TestCase):

    def test_categorize_risk_score(self):
        self.assertEqual(categorize_risk_score(15.0), "LOW")
        self.assertEqual(categorize_risk_score(45.0), "MODERATE")
        self.assertEqual(categorize_risk_score(70.0), "HIGH")
        self.assertEqual(categorize_risk_score(85.0), "VERY HIGH")
        self.assertEqual(categorize_risk_score(100.0), "VERY HIGH")

    def test_zero_rain_low_risk(self):
        res = calculate_rule_based_risk(
            observed_rain_24h_mm=0.0,
            forecast_rain_6h_mm=0.0,
            precip_probability_pct=0.0,
            soil_moisture=0.1,
            vulnerability_index=0.2,
        )
        self.assertEqual(res["predicted_risk"], 0.0)
        self.assertEqual(res["risk_level"], "LOW")
        self.assertIn("Rule-Based Risk Estimate", res["methodology"])

    def test_heavy_rain_very_high_risk(self):
        res = calculate_rule_based_risk(
            observed_rain_24h_mm=120.0,
            forecast_rain_6h_mm=50.0,
            precip_probability_pct=90.0,
            soil_moisture=0.8,
            vulnerability_index=0.75,
        )
        self.assertGreaterEqual(res["predicted_risk"], 80.0)
        self.assertEqual(res["risk_level"], "VERY HIGH")
        self.assertIn("Breakdown", res["explanation"])

    def test_missing_or_invalid_inputs(self):
        res = calculate_rule_based_risk(
            observed_rain_24h_mm=None,
            forecast_rain_6h_mm=None,
            precip_probability_pct=-20.0,
            soil_moisture=5.0,  # Should cap at 1.0
            vulnerability_index=None,
        )
        self.assertIsNotNone(res["predicted_risk"])
        self.assertIn(res["risk_level"], ["LOW", "MODERATE", "HIGH", "VERY HIGH"])


if __name__ == "__main__":
    unittest.main()
