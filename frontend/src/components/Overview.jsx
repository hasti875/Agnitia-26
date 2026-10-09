import { Section, Pill } from './ui'
import { fmtInt, RISK_CATEGORIES } from '../format'

export function Overview({ areas, risk, resources, loading, error, onRetry, updatedAt }) {
  const areaCount = areas?.areas?.length ?? 0

  // Count areas by risk category (only categories present are shown).
  const byCategory = {}
  for (const a of risk?.areas ?? []) {
    const level = (a.risk_level || 'UNKNOWN').toUpperCase()
    byCategory[level] = (byCategory[level] || 0) + 1
  }
  const categoryChips = RISK_CATEGORIES.filter((c) => byCategory[c.level]).map((c) => ({
    ...c,
    count: byCategory[c.level],
  }))

  // Totals straight from /resources.totals.
  const totals = resources?.totals || {}
  const resKeys = Object.keys(totals)
  const totalCurrent = resKeys.reduce((s, k) => s + (totals[k].total_current || 0), 0)
  const totalDeficit = resKeys.reduce((s, k) => s + (totals[k].total_deficit || 0), 0)
  const totalSurplus = resKeys.reduce((s, k) => s + (totals[k].total_surplus || 0), 0)

  const anyLoading = loading
  const anyError = error

  return (
    <Section
      title="Overview"
      subtitle="System-wide snapshot of monitored areas, risk and resource balance."
      loading={anyLoading}
      error={anyError}
      onRetry={onRetry}
      isEmpty={!anyLoading && !anyError && areaCount === 0}
      actions={
        updatedAt ? (
          <span className="muted">Last updated {updatedAt.toLocaleTimeString()}</span>
        ) : null
      }
    >
      <div className="stat-grid">
        <Pill label="Monitored areas" value={fmtInt(areaCount)} tone="primary" />
        <Pill label="Total units available" value={fmtInt(totalCurrent)} />
        <Pill label="Total deficit" value={fmtInt(totalDeficit)} tone={totalDeficit > 0 ? 'warn' : 'default'} />
        <Pill label="Total surplus" value={fmtInt(totalSurplus)} tone="ok" />
      </div>

      <h3 className="subhead">Areas by risk category</h3>
      {categoryChips.length ? (
        <ul className="chip-row" aria-label="Areas by risk category">
          {categoryChips.map((c) => (
            <li key={c.level} className={`chip chip--${c.level.toLowerCase().replace(/\s+/g, '-')}`}>
              <span aria-hidden="true">{c.marker}</span>
              <span className="chip__label">{c.label}</span>
              <span className="chip__count">{c.count}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="muted">Risk categories are not available yet.</p>
      )}

      <h3 className="subhead">Resource balance (units)</h3>
      <table className="table table--compact">
        <thead>
          <tr>
            <th scope="col">Resource</th>
            <th scope="col">Available</th>
            <th scope="col">Required</th>
            <th scope="col">Surplus</th>
            <th scope="col">Deficit</th>
          </tr>
        </thead>
        <tbody>
          {resKeys.map((k) => (
            <tr key={k}>
              <td className="label">{k.replace(/_/g, ' ')}</td>
              <td className="num">{fmtInt(totals[k].total_current)}</td>
              <td className="num">{fmtInt(totals[k].total_required)}</td>
              <td className="num num--surplus">{fmtInt(totals[k].total_surplus)}</td>
              <td className={totals[k].total_deficit ? 'num num--deficit' : 'num'}>
                {fmtInt(totals[k].total_deficit)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="footnote muted">
        Values are resource units (not currency or distance). Deficit = required − available, floored at 0.
      </p>
    </Section>
  )
}

export default Overview
