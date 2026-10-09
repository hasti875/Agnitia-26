import { Section, Pill, RiskBadge, ShortfallPill } from './ui'
import { fmtInt, RISK_CATEGORIES } from '../format'

export function Overview({ areas, risk, resources, loading, error, onRetry, updatedAt }) {
  const areaCount = areas?.areas?.length ?? 0

  // Count areas by risk category
  const byCategory = {}
  for (const a of risk?.areas ?? []) {
    const level = (a.risk_level || 'UNKNOWN').toUpperCase()
    byCategory[level] = (byCategory[level] || 0) + 1
  }
  const categoryChips = RISK_CATEGORIES.filter((c) => byCategory[c.level]).map((c) => ({
    ...c,
    count: byCategory[c.level],
  }))

  const totals = resources?.totals || {}
  const resKeys = Object.keys(totals)
  const totalCurrent = resKeys.reduce((s, k) => s + (totals[k].total_current || 0), 0)
  const totalDeficit = resKeys.reduce((s, k) => s + (totals[k].total_deficit || 0), 0)
  const totalSurplus = resKeys.reduce((s, k) => s + (totals[k].total_surplus || 0), 0)

  return (
    <Section
      id="overview"
      title="System Overview"
      subtitle="System-wide snapshot of monitored regions, flood risk distribution, and emergency inventory balance."
      loading={loading}
      error={error}
      onRetry={onRetry}
      isEmpty={!loading && !error && areaCount === 0}
      actions={
        updatedAt ? (
          <span className="status-badge" style={{ fontSize: '0.78rem' }}>
            <span className="status-dot" />
            Updated {updatedAt.toLocaleTimeString()}
          </span>
        ) : null
      }
    >
      <div className="stat-grid">
        <Pill label="Monitored Areas" value={fmtInt(areaCount)} tag="8 Active" tone="teal" />
        <Pill label="Total Units Deployed" value={fmtInt(totalCurrent)} tag="Inventory" tone="ok" />
        <Pill label="Total Deficit" value={fmtInt(totalDeficit)} tag={totalDeficit > 0 ? '⚠️ High' : '✓ None'} tone={totalDeficit > 0 ? 'danger' : 'ok'} />
        <Pill label="Total Surplus" value={fmtInt(totalSurplus)} tag="Available" tone="teal" />
      </div>

      <div style={{ margin: '24px 0 16px' }}>
        <h3 style={{ fontSize: '1rem', fontWeight: 800, margin: '0 0 12px', color: '#0f172a' }}>
          Areas by Risk Category
        </h3>
        {categoryChips.length ? (
          <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
            {categoryChips.map((c) => (
              <div
                key={c.level}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '8px',
                  padding: '6px 14px',
                  borderRadius: '999px',
                  background: '#ffffff',
                  border: '1px solid var(--border)',
                  boxShadow: 'var(--shadow-sm)',
                  fontSize: '0.85rem',
                  fontWeight: 600
                }}
              >
                <RiskBadge level={c.level} />
                <span style={{ fontWeight: 800, color: '#0f172a' }}>{c.count} Wards</span>
              </div>
            ))}
          </div>
        ) : (
          <p className="muted">Risk categories are not available yet.</p>
        )}
      </div>

      <div style={{ marginTop: '24px' }}>
        <h3 style={{ fontSize: '1rem', fontWeight: 800, margin: '0 0 12px', color: '#0f172a' }}>
          Resource Balance Breakdown
        </h3>
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th scope="col">Resource Type</th>
                <th scope="col" style={{ textAlign: 'right' }}>Available (Units)</th>
                <th scope="col" style={{ textAlign: 'right' }}>Required (Units)</th>
                <th scope="col" style={{ textAlign: 'right' }}>Surplus</th>
                <th scope="col" style={{ textAlign: 'right' }}>Deficit</th>
              </tr>
            </thead>
            <tbody>
              {resKeys.map((k) => (
                <tr key={k}>
                  <td className="label" style={{ textTransform: 'capitalize' }}>
                    {k.replace(/_/g, ' ')}
                  </td>
                  <td className="num">{fmtInt(totals[k].total_current)}</td>
                  <td className="num">{fmtInt(totals[k].total_required)}</td>
                  <td className="num" style={{ color: '#059669' }}>+{fmtInt(totals[k].total_surplus)}</td>
                  <td className="num" style={{ color: totals[k].total_deficit ? '#ef4444' : 'inherit' }}>
                    {fmtInt(totals[k].total_deficit)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </Section>
  )
}

export default Overview
