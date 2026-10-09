import { describe, it, expect } from 'vitest'
import {
    categorizeRiskScore,
    calculateRuleBasedRisk,
    DEFAULT_THRESHOLDS,
    METHODOLOGY_DISCLAIMER,
} from './riskCalculator'

describe('riskCalculator Utility', () => {
    it('correctly categorizes scores into LOW, MODERATE, HIGH, and VERY HIGH', () => {
        expect(categorizeRiskScore(10)).toBe('LOW')
        expect(categorizeRiskScore(45)).toBe('MODERATE')
        expect(categorizeRiskScore(75)).toBe('HIGH')
        expect(categorizeRiskScore(90)).toBe('VERY HIGH')
    })

    it('calculates zero risk when rainfall is zero', () => {
        const result = calculateRuleBasedRisk({
            observed_rain_24h_mm: 0,
            forecast_rain_6h_mm: 0,
            precip_probability_pct: 0,
            soil_moisture: 0,
            vulnerability_index: 0.2,
        })

        expect(result.predicted_risk).toBe(0)
        expect(result.risk_level).toBe('LOW')
        expect(result.methodology).toBe(METHODOLOGY_DISCLAIMER)
    })

    it('calculates VERY HIGH risk during extreme rainfall and high vulnerability', () => {
        const result = calculateRuleBasedRisk({
            observed_rain_24h_mm: 120,
            forecast_rain_6h_mm: 60,
            precip_probability_pct: 95,
            soil_moisture: 0.9,
            vulnerability_index: 0.8,
        })

        expect(result.predicted_risk).toBeGreaterThanOrEqual(80)
        expect(result.risk_level).toBe('VERY HIGH')
        expect(result.explanation).toContain('Breakdown')
    })

    it('handles invalid or missing inputs gracefully', () => {
        const result = calculateRuleBasedRisk({
            observed_rain_24h_mm: null,
            forecast_rain_6h_mm: undefined,
            precip_probability_pct: -50,
            soil_moisture: 'invalid',
        })

        expect(typeof result.predicted_risk).toBe('number')
        expect(['LOW', 'MODERATE', 'HIGH', 'VERY HIGH']).toContain(result.risk_level)
    })
})
