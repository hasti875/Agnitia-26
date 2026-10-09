/**
 * riskCalculator.js
 * =================
 * Rule-based flood risk calculation utility for the frontend dashboard.
 *
 * Configurable thresholds:
 * - LOW: Score < 30
 * - MODERATE: 30 <= Score < 60
 * - HIGH: 60 <= Score < 80
 * - VERY HIGH: Score >= 80
 *
 * Explicitly labeled as a Rule-Based Risk Estimate (Uncalibrated Prototype).
 */

export const DEFAULT_THRESHOLDS = {
    LOW_MAX: 30,
    MODERATE_MAX: 60,
    HIGH_MAX: 80,
}

export const METHODOLOGY_DISCLAIMER =
    'Rule-Based Risk Estimate (Uncalibrated Prototype). Calculated dynamically from Open-Meteo observed rainfall, 6h forecast, soil moisture, and static vulnerability index.'

/**
 * Categorize numerical risk score (0-100) into Low, Moderate, High, or Very High.
 */
export function categorizeRiskScore(score, thresholds = DEFAULT_THRESHOLDS) {
    const val = Number(score) || 0
    if (val < (thresholds.LOW_MAX ?? 30)) return 'LOW'
    if (val < (thresholds.MODERATE_MAX ?? 60)) return 'MODERATE'
    if (val < (thresholds.HIGH_MAX ?? 80)) return 'HIGH'
    return 'VERY HIGH'
}

/**
 * Calculate deterministic rule-based risk score (0-100).
 */
export function calculateRuleBasedRisk({
    observed_rain_24h_mm = 0,
    forecast_rain_6h_mm = 0,
    precip_probability_pct = 0,
    soil_moisture = 0,
    vulnerability_index = 0.5,
    thresholds = DEFAULT_THRESHOLDS,
} = {}) {
    const obs = Math.max(0, Number(observed_rain_24h_mm) || 0)
    const fc = Math.max(0, Number(forecast_rain_6h_mm) || 0)
    const prob = Math.max(0, Math.min(100, Number(precip_probability_pct) || 0))
    const soil = Math.max(0, Math.min(1, Number(soil_moisture) || 0))
    const vuln = Math.max(0, Math.min(1, Number(vulnerability_index) || 0.5))

    const rainfallMetric = obs * 0.4 + fc * 0.6
    const rainfallIndex = Math.min(50, rainfallMetric * 1.5)
    const soilFactor = 1.0 + soil * 0.3
    const probFactor = 0.8 + (prob / 100) * 0.4
    const vulnFactor = 1.0 + vuln * 0.5

    const rawScore = rainfallIndex * soilFactor * probFactor * vulnFactor
    const finalScore = Number(Math.min(100, Math.max(0, rawScore)).toFixed(1))
    const riskLevel = categorizeRiskScore(finalScore, thresholds)

    const explanation =
        `Rule-Based Calculation Breakdown: Observed Rain (24h)=${obs}mm, Forecast Rain (6h)=${fc}mm ` +
        `-> Rainfall Index=${rainfallIndex.toFixed(1)}/50; Soil Factor=${soilFactor.toFixed(2)}x; ` +
        `Precip Prob=${prob}% (${probFactor.toFixed(2)}x); Vulnerability=${vuln.toFixed(2)} (${vulnFactor.toFixed(2)}x). ` +
        `Final Risk Index=${finalScore}/100 [${riskLevel}].`

    return {
        predicted_risk: finalScore,
        risk_level: riskLevel,
        methodology: METHODOLOGY_DISCLAIMER,
        explanation,
        components: {
            observed_rain_24h_mm: obs,
            forecast_rain_6h_mm: fc,
            precip_probability_pct: prob,
            soil_moisture: soil,
            vulnerability_index: vuln,
            rainfall_index: Number(rainfallIndex.toFixed(2)),
            soil_factor: Number(soilFactor.toFixed(2)),
            prob_factor: Number(probFactor.toFixed(2)),
            vuln_factor: Number(vulnFactor.toFixed(2)),
        },
    }
}
