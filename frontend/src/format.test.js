import { fmtInt, fmtNum, fmtPct, riskMeta, RISK_CATEGORIES } from './format'

describe('format helpers', () => {
  it('fmtInt handles null/undefined/NaN', () => {
    expect(fmtInt(null)).toBe('—')
    expect(fmtInt(undefined)).toBe('—')
    expect(fmtInt(NaN)).toBe('—')
    expect(fmtInt(1234)).toBe('1,234')
  })

  it('fmtNum avoids false precision and handles missing', () => {
    expect(fmtNum(null)).toBe('—')
    expect(fmtNum(0.1, 4)).toBe('0.1')
    expect(fmtNum(1234.5678, 2)).toBe('1,234.57')
  })

  it('fmtPct formats percentages', () => {
    expect(fmtPct(5.65)).toBe('5.7%')
    expect(fmtPct(null)).toBe('—')
  })

  it('riskMeta falls back for unknown levels (no color-only reliance)', () => {
    expect(riskMeta('LOW').label).toBe('Low')
    expect(riskMeta('CRITICAL').marker).toBeTruthy()
    expect(riskMeta('WEIRD').label).toBe('WEIRD')
  })

  it('exposes all five documented risk categories', () => {
    expect(RISK_CATEGORIES.map((c) => c.level)).toEqual([
      'LOW', 'MODERATE', 'HIGH', 'VERY HIGH', 'CRITICAL',
    ])
  })
})
