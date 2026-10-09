import { useState } from 'react'
import { Section, RiskBadge } from './ui'
import { fmtNum } from '../format'

// Explanations — human-readable text from /explanations, in expandable cards.
export function Explanations({ explanations, loading, error, onRetry }) {
  const [open, setOpen] = useState({})
  const e = explanations

  function toggle(key) { setOpen((o) => ({ ...o, [key]: !o[key] })) }

  if (!loading && !error && !e) return null

  return (
    <Section
      title="Explanations"
      subtitle="Plain-language summaries generated from the existing engine outputs."
      loading={loading}
      error={error}
      onRetry={onRetry}
      isEmpty={!loading && !error && !e}
    >
      {e?.disclaimer ? (
        <p className="callout callout--note" role="note">{e.disclaimer}</p>
      ) : null}

      {/* Area risk */}
      {Array.isArray(e?.area_risk) && e.area_risk.length > 0 && (
        <div className="explain-group">
          <h3 className="subhead">Area risk</h3>
          <div className="cards">
            {e.area_risk.map((a) => {
              const key = `risk-${a.area_id}`
              return (
                <Card key={key} title={a.area_name} open={!!open[key]} onToggle={() => toggle(key)} badge={<RiskBadge level={a.risk_level} />}>
                  {a.limitation ? <p className="muted">Limitation: {a.limitation}</p> : null}
                  <p>{a.explanation}</p>
                  {a.predicted_risk !== null && a.predicted_risk !== undefined ? (
                    <p className="muted mono">Predicted risk: {fmtNum(a.predicted_risk, 1)} / 100</p>
                  ) : null}
                </Card>
              )
            })}
          </div>
        </div>
      )}

      {/* Resource shortages */}
      {e?.resource_shortages && (
        <div className="explain-group">
          <h3 className="subhead">Resource shortages</h3>
          <p>{e.resource_shortages.summary}</p>
          {e.resource_shortages.limitation ? <p className="muted">Limitation: {e.resource_shortages.limitation}</p> : null}
          <div className="cards">
            {(e.resource_shortages.areas ?? []).map((a) => {
              const key = `short-${a.area_id}`
              return (
                <Card key={key} title={a.area_name} open={!!open[key]} onToggle={() => toggle(key)}>
                  <p>{a.explanation}</p>
                  {a.shortages?.length ? (
                    <ul className="plain-list">
                      {a.shortages.map((s) => (
                        <li key={s.resource}>
                          {s.deficit} short on {s.resource.replace(/_/g, ' ')} (has {s.current}, needs {s.required})
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

      {/* Transfers */}
      {Array.isArray(e?.transfers) && e.transfers.length > 0 && (
        <div className="explain-group">
          <h3 className="subhead">Transfer recommendations</h3>
          <div className="cards">
            {e.transfers.map((t, i) => {
              const key = `move-${i}`
              return (
                <Card key={key} title={`${t.quantity} ${t.resource?.replace(/_/g, ' ')}: ${t.from_area} → ${t.to_area}`} open={!!open[key]} onToggle={() => toggle(key)}>
                  {t.limitation ? <p className="muted">Limitation: {t.limitation}</p> : null}
                  <p>{t.explanation}</p>
                </Card>
              )
            })}
          </div>
        </div>
      )}

      {/* Allocation comparison */}
      {e?.allocation_comparison && (
        <div className="explain-group">
          <h3 className="subhead">Allocation comparison</h3>
          <p>{e.allocation_comparison.explanation}</p>
          {e.allocation_comparison.limitation ? (
            <p className="muted">Limitation: {e.allocation_comparison.limitation}</p>
          ) : null}
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
        <span className="card__chevron" aria-hidden="true">{open ? '−' : '+'}</span>
      </button>
      {open ? <div className="card__body">{children}</div> : null}
    </div>
  )
}

export default Explanations
