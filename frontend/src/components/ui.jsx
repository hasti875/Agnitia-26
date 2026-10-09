import { riskMeta } from '../format'

// Section — a titled, carded dashboard panel that owns its loading / error /
// empty state so a failing endpoint only affects its own panel.
export function Section({ title, subtitle, loading, error, isEmpty, onRetry, children, actions }) {
  return (
    <section className="section" aria-busy={loading || undefined}>
      <header className="section__head">
        <div>
          <h2 className="section__title">{title}</h2>
          {subtitle ? <p className="section__subtitle">{subtitle}</p> : null}
        </div>
        {actions ? <div className="section__actions">{actions}</div> : null}
      </header>

      {loading ? (
        <div className="state state--loading" role="status">
          <span className="spinner" aria-hidden="true" /> Loading…
        </div>
      ) : error ? (
        <div className="state state--error" role="alert">
          <strong>Could not load this section.</strong>
          <p>{error}</p>
          {onRetry ? (
            <button type="button" className="btn" onClick={onRetry}>
              Try again
            </button>
          ) : null}
        </div>
      ) : isEmpty ? (
        <div className="state state--empty">No data available.</div>
      ) : (
        <div className="section__body">{children}</div>
      )}
    </section>
  )
}

// RiskBadge — text label + unicode marker (never color alone).
export function RiskBadge({ level }) {
  const meta = riskMeta(level)
  return (
    <span className={`risk-badge risk-badge--${meta.level.toLowerCase().replace(/\s+/g, '-')}`} title={`Risk: ${meta.label}`}>
      <span aria-hidden="true">{meta.marker}</span>
      <span>{meta.label}</span>
    </span>
  )
}

// Pill — a small labelled value chip.
export function Pill({ label, value, tone = 'default' }) {
  return (
    <div className={`pill pill--${tone}`}>
      <span className="pill__label">{label}</span>
      <span className="pill__value">{value}</span>
    </div>
  )
}

// DeficitTag — highlights a shortage value.
export function DeficitTag({ value }) {
  if (!value) return <span className="num num--ok">0</span>
  return <span className="num num--deficit">{value}</span>
}

export function SurplusTag({ value }) {
  if (!value) return <span className="num num--ok">0</span>
  return <span className="num num--surplus">+{value}</span>
}
