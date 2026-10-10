import { Section, Pill } from './ui'
import { fmtNum, fmtPct } from '../format'

export function Comparison({ comparison, loading, error, onRetry }) {
  const c = comparison
  const improved = c?.improved_areas ?? c?.area_results?.filter((a) => a.impact_change < 0).map((a) => a.area_name) ?? []
  const worsened = c?.worsened_areas ?? c?.area_results?.filter((a) => a.impact_change > 0).map((a) => a.area_name) ?? []
  const reduction = c?.absolute_reduction
  const isImprovement = reduction !== undefined && reduction > 0

  return (
    <Section
      id="comparison"
      title="Impact & Arbitrage Comparison"
      subtitle="Fixed static allocation vs optimized dynamic allocation — measured risk-impact reduction across the Seven Sister States."
      loading={loading}
      error={error}
      onRetry={onRetry}
      isEmpty={!loading && !error && !c}
    >
      <div className="callout callout--note">
        <strong>Live Risk Arbitrage:</strong> Compares fixed static allocation against OR-Tools optimised dynamic allocation using real-time weather-driven risk scores across the Seven Sister States.
      </div>

      <div className="stat-grid">
        <Pill label="Fixed Allocation Risk" value={fmtNum(c?.fixed_risk_impact, 2)} tag="Baseline" tone="yellow" />
        <Pill label="Optimized Allocation Risk" value={fmtNum(c?.optimized_risk_impact, 2)} tag="Arbitraged" tone="teal" />
        <Pill label="Absolute Risk Reduction" value={fmtNum(reduction, 2)} tag="Net Saved" tone={isImprovement ? 'ok' : 'teal'} />
        <Pill label="Percentage Reduction" value={fmtPct(c?.percentage_reduction)} tag="Efficiency Gain" tone={isImprovement ? 'ok' : 'teal'} />
      </div>

      {(improved.length > 0 || worsened.length > 0) && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px', marginTop: '20px' }}>
          <div style={{ background: '#ecfdf5', padding: '16px 20px', borderRadius: '14px', border: '1px solid #a7f3d0' }}>
            <h4 style={{ margin: '0 0 10px', color: '#047857', fontWeight: 800 }}>Areas with Reduced Risk Impact</h4>
            {improved.length ? (
              <ul style={{ margin: 0, paddingLeft: '20px', color: '#065f46', fontSize: '0.9rem' }}>
                {improved.map((n) => <li key={n} style={{ margin: '4px 0' }}>{n}</li>)}
              </ul>
            ) : <p className="muted">None</p>}
          </div>

          <div style={{ background: '#fff1f2', padding: '16px 20px', borderRadius: '14px', border: '1px solid #fecdd3' }}>
            <h4 style={{ margin: '0 0 10px', color: '#be123c', fontWeight: 800 }}>Areas with Higher Risk Impact</h4>
            {worsened.length ? (
              <ul style={{ margin: 0, paddingLeft: '20px', color: '#9f1239', fontSize: '0.9rem' }}>
                {worsened.map((n) => <li key={n} style={{ margin: '4px 0' }}>{n}</li>)}
              </ul>
            ) : <p style={{ color: '#047857', fontSize: '0.88rem', margin: 0 }}>✓ No areas experienced increased risk</p>}
          </div>
        </div>
      )}
    </Section>
  )
}

export default Comparison
