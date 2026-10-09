import { Section, Pill } from './ui'
import { fmtNum, fmtPct } from '../format'

// Comparison — fixed vs optimized Estimated Prototype Risk-Impact Metric.
export function Comparison({ comparison, loading, error, onRetry }) {
  const c = comparison
  const improved = c?.improved_areas ?? c?.area_results?.filter((a) => a.impact_change < 0).map((a) => a.area_name) ?? []
  const worsened = c?.worsened_areas ?? c?.area_results?.filter((a) => a.impact_change > 0).map((a) => a.area_name) ?? []
  const reduction = c?.absolute_reduction
  const isImprovement = reduction !== undefined && reduction > 0

  return (
    <Section
      title="Impact comparison"
      subtitle="Fixed allocation vs optimized allocation under the estimated prototype risk-impact metric."
      loading={loading}
      error={error}
      onRetry={onRetry}
      isEmpty={!loading && !error && !c}
    >
      <div className="callout callout--note" role="note">
        <strong>Estimated metric, synthetic data.</strong> This is a prototype
        risk-impact estimate for demonstration. It does <em>not</em> represent
        lives saved, guaranteed prevention, or verified real-world risk reduction.
      </div>

      <div className="stat-grid">
        <Pill label="Fixed allocation impact" value={fmtNum(c?.fixed_risk_impact, 4)} />
        <Pill label="Optimized allocation impact" value={fmtNum(c?.optimized_risk_impact, 4)} tone="primary" />
        <Pill label="Absolute reduction" value={fmtNum(reduction, 4)} tone={isImprovement ? 'ok' : 'default'} />
        <Pill label="Percentage reduction" value={fmtPct(c?.percentage_reduction)} tone={isImprovement ? 'ok' : 'default'} />
      </div>

      {c?.metric_name ? <p className="muted">Metric: <span className="mono">{c.metric_name}</span></p> : null}

      {(improved.length > 0 || worsened.length > 0) && (
        <div className="two-col">
          <div>
            <h3 className="subhead">Areas with lower impact</h3>
            {improved.length ? (
              <ul className="plain-list">{improved.map((n) => <li key={n}>{n}</li>)}</ul>
            ) : <p className="muted">None</p>}
          </div>
          <div>
            <h3 className="subhead">Areas with higher impact</h3>
            {worsened.length ? (
              <ul className="plain-list">{worsened.map((n) => <li key={n}>{n}</li>)}</ul>
            ) : <p className="muted">None</p>}
          </div>
        </div>
      )}

      {c?.limitations?.length ? (
        <details className="details">
          <summary>Assumptions &amp; limitations</summary>
          <ul className="plain-list">
            {(c.assumptions ?? []).map((a, i) => <li key={`a${i}`}>{a}</li>)}
            {(c.limitations ?? []).map((l, i) => <li key={`l${i}`}>{l}</li>)}
          </ul>
        </details>
      ) : null}
    </Section>
  )
}

export default Comparison
