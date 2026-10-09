// format.js — consistent number formatting + risk-category presentation.
// Avoids implying false precision and never relies on color alone (each
// category also carries a text label and a unicode marker).

export function fmtInt(n) {
  if (n === null || n === undefined || Number.isNaN(Number(n))) return '—'
  return Math.round(Number(n)).toLocaleString('en-US')
}

export function fmtNum(n, digits = 2) {
  if (n === null || n === undefined || Number.isNaN(Number(n))) return '—'
  return Number(n).toLocaleString('en-US', {
    minimumFractionDigits: 0,
    maximumFractionDigits: digits,
  })
}

export function fmtPct(n, digits = 1) {
  if (n === null || n === undefined || Number.isNaN(Number(n))) return '—'
  return `${Number(n).toLocaleString('en-US', { maximumFractionDigits: digits })}%`
}

// Risk categories use a marker + label (not color alone) for accessibility.
export const RISK_CATEGORIES = [
  { level: 'LOW', marker: '●', label: 'Low' },
  { level: 'MODERATE', marker: '▲', label: 'Moderate' },
  { level: 'HIGH', marker: '◆', label: 'High' },
  { level: 'VERY HIGH', marker: '⬆', label: 'Very High' },
  { level: 'CRITICAL', marker: '⚠', label: 'Critical' },
]

export function riskMeta(level) {
  const found = RISK_CATEGORIES.find((c) => c.level === (level || '').toUpperCase())
  if (found) return found
  return { level: level || 'UNKNOWN', marker: '○', label: level || 'Unknown' }
}
