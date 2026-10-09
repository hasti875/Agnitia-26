import { useState } from 'react'
import { Section, RiskBadge } from './ui'
import { fmtNum } from '../format'

export function Explanations({ explanations, loading, error, onRetry }) {
  const [open, setOpen] = useState({ 'risk-A2': true, 'short-A2': true })
  const e = explanations

  function toggle(key) { setOpen((o) => ({ ...o, [key]: !o[key] })) }

  if (!loading && !error && !e) return null

  return (
    <Section
      id="explanations"
      title="Automated Decision Explanations"
      subtitle="Plain-language AI summaries explaining risk projections and transfer rationales."
      loading={loading}
      error={error}
      onRetry={onRetry}
      isEmpty={!loading && !error && !e}
    >
      {e?.disclaimer ? (
        <p className="callout callout--note">{e.disclaimer}</p>
      ) : null}

      {/* Area risk */}
      {Array.isArray(e?.area_risk) && e.area_risk.length > 0 && (
        <div style={{ marginBottom: '24px' }}>
          <h3 style={{ fontSize: '1rem', fontWeight: 800, margin: '0 0 12px', color: '#0f172a' }}>Regional Flood Risk Rationale</h3>
          <div className="cards">
            {e.area_risk.map((a) => {
              const key = `risk-${a.area_id}`
              return (
                <Card key={key} title={a.area_name} open={!!open[key]} onToggle={() => toggle(key)} badge={<RiskBadge level={a.risk_level} />}>
                  <p style={{ margin: '6px 0', lineHeight: 1.6 }}>{a.explanation}</p>
                  {a.predicted_risk !== null && a.predicted_risk !== undefined ? (
                    <p className="muted" style={{ fontSize: '0.8rem', margin: '6px 0 0' }}>Predicted Risk Score: <strong>{fmtNum(a.predicted_risk, 1)} / 100</strong></p>
                  ) : null}
                </Card>
              )
            })}
          </div>
        </div>
      )}

      {/* Resource shortages */}
      {e?.resource_shortages && (
        <div style={{ marginBottom: '24px' }}>
          <h3 style={{ fontSize: '1rem', fontWeight: 800, margin: '0 0 6px', color: '#0f172a' }}>Resource Shortage Summaries</h3>
          <p className="muted" style={{ margin: '0 0 12px', fontSize: '0.88rem' }}>{e.resource_shortages.summary}</p>
          <div className="cards">
            {(e.resource_shortages.areas ?? []).map((a) => {
              const key = `short-${a.area_id}`
              return (
                <Card key={key} title={a.area_name} open={!!open[key]} onToggle={() => toggle(key)}>
                  <p style={{ margin: '6px 0', lineHeight: 1.6 }}>{a.explanation}</p>
                  {a.shortages?.length ? (
                    <ul style={{ margin: '8px 0 0', paddingLeft: '18px', fontSize: '0.85rem' }}>
                      {a.shortages.map((s) => (
                        <li key={s.resource} style={{ margin: '4px 0' }}>
                          <strong style={{ color: '#b91c1c' }}>{s.deficit} short</strong> on {s.resource.replace(/_/g, ' ')} (has {s.current}, required {s.required})
                        </li>
                      ))}
                    </ul>
                  ) : null}
                </Card>
              )
            })}
          </div>
        </div>
      )}
    </Section>
  )
}

function Card({ title, badge, open, onToggle, children }) {
  return (
    <div className="card">
      <button type="button" className="card__head" aria-expanded={open} onClick={onToggle}>
        <span className="card__title">{title}</span>
        {badge}
        <span style={{ fontSize: '1.2rem', color: '#64748b', fontWeight: 700 }}>{open ? '−' : '+'}</span>
      </button>
      {open ? <div className="card__body">{children}</div> : null}
    </div>
  )
}

export default Explanations
