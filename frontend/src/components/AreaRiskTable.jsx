import { useState } from 'react'
import { Section, RiskBadge } from './ui'
import { fmtNum } from '../format'

// AreaRiskTable — all eight areas with predicted risk, category and the extra
// static details the API provides (population, density, vulnerability).
// Columns are sortable (click a header) but the default order is by risk.
export function AreaRiskTable({ risk, areas, loading, error, onRetry }) {
  const [sortKey, setSortKey] = useState('predicted_risk')
  const [sortDir, setSortDir] = useState('desc')

  // Merge /risk with /areas static detail by area_id.
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
    { key: 'area_name', label: 'Area' },
    { key: 'predicted_risk', label: 'Predicted risk' },
    { key: 'risk_level', label: 'Category' },
    { key: 'population', label: 'Population (000s)' },
    { key: 'population_density', label: 'Density (/km²)' },
    { key: 'vulnerability_index', label: 'Vulnerability' },
  ]

  function toggleSort(key) {
    if (key === sortKey) setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    else { setSortKey(key); setSortDir(key === 'area_name' || key === 'risk_level' ? 'asc' : 'desc') }
  }

  return (
    <Section
      title="Area risk"
      subtitle="6-hour-ahead predicted flood risk per area (model forecast)."
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
                <th key={h.key} scope="col" aria-sort={sortKey === h.key ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none'}>
                  <button type="button" className="th-sort" onClick={() => toggleSort(h.key)}>
                    {h.label}
                    <span className="th-sort__arrow" aria-hidden="true">
                      {sortKey === h.key ? (sortDir === 'asc' ? '▲' : '▼') : '↕'}
                    </span>
                  </button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sorted.map((r) => (
              <tr key={r.area_id}>
                <td className="label">
                  {r.area_name}
                  <span className="muted mono"> ({r.area_id})</span>
                </td>
                <td className="num">{fmtNum(r.predicted_risk, 1)}<span className="muted"> /100</span></td>
                <td><RiskBadge level={r.risk_level} /></td>
                <td className="num">{fmtNum(r.population, 0)}</td>
                <td className="num">{fmtNum(r.population_density, 0)}</td>
                <td className="num">{fmtNum(r.vulnerability_index, 2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="footnote muted">
        Risk is a model prediction on a 0–100 scale. Category is shown with a marker and text label, not color alone.
      </p>
    </Section>
  )
}

export default AreaRiskTable
