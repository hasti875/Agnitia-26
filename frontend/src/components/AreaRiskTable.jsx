import { useState } from 'react'
import { Section, RiskBadge } from './ui'
import { fmtNum } from '../format'

export function AreaRiskTable({ risk, areas, loading, error, onRetry }) {
  const [sortKey, setSortKey] = useState('predicted_risk')
  const [sortDir, setSortDir] = useState('desc')

  const staticById = {}
  for (const a of areas?.areas ?? []) staticById[a.area_id] = a

  const rows = (risk?.areas ?? []).map((r) => ({ ...r, ...staticById[r.area_id] }))

  const sorted = [...rows].sort((a, b) => {
    let av = a[sortKey]
    let bv = b[sortKey]
    if (typeof av === 'string') { av = av.toLowerCase(); bv = (bv || '').toLowerCase() }
    if (av === bv) return 0
    const cmp = av > bv ? 1 : -1
    return sortDir === 'asc' ? cmp : -cmp
  })

  const headers = [
    { key: 'area_name', label: 'Area / Location' },
    { key: 'predicted_risk', label: '6h Risk Index' },
    { key: 'risk_level', label: 'Category' },
    { key: 'obs_rain', label: 'Observed Rain (24h)' },
    { key: 'fc_rain', label: 'Forecast Rain (6h)' },
    { key: 'vulnerability_index', label: 'Vulnerability' },
  ]

  function toggleSort(key) {
    if (key === sortKey) setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    else { setSortKey(key); setSortDir(key === 'area_name' || key === 'risk_level' ? 'asc' : 'desc') }
  }

  return (
    <Section
      id="area-risk"
      title="Regional Risk & Weather Telemetry"
      subtitle="Deterministic rule-based risk scores calculated from Open-Meteo rainfall telemetry and static area vulnerability."
      loading={loading}
      error={error}
      onRetry={onRetry}
      isEmpty={!loading && !error && rows.length === 0}
    >
      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              {headers.map((h) => (
                <th key={h.key} scope="col">
                  <button
                    type="button"
                    style={{
                      background: 'none',
                      border: 'none',
                      padding: 0,
                      font: 'inherit',
                      fontWeight: 'inherit',
                      color: 'inherit',
                      cursor: 'pointer',
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: '4px'
                    }}
                    onClick={() => toggleSort(h.key)}
                  >
                    {h.label}
                    <span style={{ fontSize: '0.7rem', opacity: 0.7 }}>
                      {sortKey === h.key ? (sortDir === 'asc' ? '▲' : '▼') : '↕'}
                    </span>
                  </button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sorted.map((r) => {
              const obsRain = r.components?.observed_rain_24h_mm ?? r.obs_rain ?? 0.0
              const fcRain = r.components?.forecast_rain_6h_mm ?? r.fc_rain ?? 0.0
              return (
                <tr key={r.area_id}>
                  <td className="label">
                    {r.area_name}
                    <span className="muted" style={{ fontSize: '0.8rem', marginLeft: '6px' }}>({r.area_id})</span>
                  </td>
                  <td className="num" style={{ fontWeight: 800 }}>
                    {fmtNum(r.predicted_risk, 1)}<span className="muted">/100</span>
                  </td>
                  <td><RiskBadge level={r.risk_level} /></td>
                  <td className="num">{fmtNum(obsRain, 1)} mm</td>
                  <td className="num">{fmtNum(fcRain, 1)} mm</td>
                  <td className="num">{fmtNum(r.vulnerability_index, 2)}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </Section>
  )
}

export default AreaRiskTable
