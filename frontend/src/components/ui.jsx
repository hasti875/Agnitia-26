import { riskMeta } from '../format'

export function Section({ title, subtitle, loading, error, isEmpty, onRetry, children, actions, id }) {
  return (
    <section className="section" id={id} aria-busy={loading || undefined}>
      <header className="section__head">
        <div>
          <h2 className="section__title">{title}</h2>
          {subtitle ? <p className="section__subtitle">{subtitle}</p> : null}
        </div>
        {actions ? <div className="section__actions">{actions}</div> : null}
      </header>

      {loading ? (
        <div className="state state--loading" role="status" style={{ padding: '24px', textAlign: 'center' }}>
          <span className="spinner" aria-hidden="true" /> Loading section data…
        </div>
      ) : error ? (
        <div className="state state--error" role="alert" style={{ padding: '24px', textAlign: 'center' }}>
          <strong>Could not connect to live backend.</strong>
          <p>{error}</p>
          {onRetry ? (
            <button type="button" className="btn btn--primary" onClick={onRetry}>
              Try again
            </button>
          ) : null}
        </div>
      ) : isEmpty ? (
        <div className="state state--empty" style={{ padding: '24px', textAlign: 'center', color: '#64748b' }}>
          No data available.
        </div>
      ) : (
        <div className="section__body">{children}</div>
      )}
    </section>
  )
}

export function RiskBadge({ level }) {
  const meta = riskMeta(level)
  const toneClass = (level || '').toUpperCase() === 'CRITICAL' ? 'red' :
    (level || '').toUpperCase().includes('HIGH') ? 'orange' :
      (level || '').toUpperCase() === 'MODERATE' ? 'yellow' : 'green'
  return (
    <span className={`tag-badge tag-badge--${toneClass}`} title={`Risk: ${meta.label}`}>
      <span aria-hidden="true">{meta.marker}</span>
      <span>{meta.label}</span>
    </span>
  )
}

export function Pill({ label, value, tag, tone = 'default' }) {
  return (
    <div className="pill-card">
      <span className="pill-card__label">{label}</span>
      <div className="pill-card__content">
        <span className="pill-card__value">{value}</span>
        {tag ? (
          <span className={`tag-badge tag-badge--${tone}`}>
            {tag}
          </span>
        ) : null}
      </div>
    </div>
  )
}

export function ProgressBar({ current, max, status }) {
  const percentage = Math.min(100, Math.max(0, max > 0 ? (current / max) * 100 : 0))
  const fillTone = status === 'danger' ? 'progress-bar-fill--danger' :
    status === 'warning' ? 'progress-bar-fill--warning' : ''
  return (
    <div className="progress-cell">
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.78rem', color: '#475569', fontWeight: 600 }}>
        <span>{current} / {max}</span>
        <span>{Math.round(percentage)}%</span>
      </div>
      <div className="progress-bar-bg">
        <div className={`progress-bar-fill ${fillTone}`} style={{ width: `${percentage}%` }} />
      </div>
    </div>
  )
}

export function ShortfallPill({ deficit, surplus }) {
  if (deficit > 0) {
    return <span className="shortfall-pill shortfall-pill--deficit">⚠️ {deficit} deficit</span>
  }
  if (surplus > 0) {
    return <span className="shortfall-pill shortfall-pill--surplus">✓ +{surplus} surplus</span>
  }
  return <span className="shortfall-pill shortfall-pill--covered">✓ Covered</span>
}

export function DeficitTag({ value }) {
  if (!value) return <span className="num muted">0</span>
  return <span className="num" style={{ color: '#b91c1c', fontWeight: 700 }}>{value}</span>
}

export function SurplusTag({ value }) {
  if (!value) return <span className="num muted">0</span>
  return <span className="num" style={{ color: '#047857', fontWeight: 700 }}>+{value}</span>
}
