import { useState, useRef } from 'react'
import { cityRisk } from '../api'

const RISK_COLORS = {
  LOW:         { grad: 'linear-gradient(135deg,#16a34a,#4ade80)', badge: '#16a34a', glow: 'rgba(22,163,74,0.2)',  bar: '#4ade80' },
  MODERATE:    { grad: 'linear-gradient(135deg,#ca8a04,#facc15)', badge: '#ca8a04', glow: 'rgba(202,138,4,0.2)',  bar: '#facc15' },
  HIGH:        { grad: 'linear-gradient(135deg,#ea580c,#fb923c)', badge: '#ea580c', glow: 'rgba(234,88,12,0.2)',  bar: '#fb923c' },
  'VERY HIGH': { grad: 'linear-gradient(135deg,#dc2626,#f87171)', badge: '#dc2626', glow: 'rgba(220,38,38,0.2)',  bar: '#f87171' },
  CRITICAL:    { grad: 'linear-gradient(135deg,#7c3aed,#dc2626)', badge: '#b91c1c', glow: 'rgba(124,58,237,0.25)',bar: '#a855f7' },
}

const QUICK_CITIES = [
  { name: 'Guwahati', icon: '🌊' }, { name: 'Mumbai', icon: '🏙️' },
  { name: 'Chennai', icon: '🌊' },  { name: 'Kolkata', icon: '🌧️' },
  { name: 'Patna', icon: '🌊' },    { name: 'Bhubaneswar', icon: '🌦️' },
  { name: 'Surat', icon: '🌊' },    { name: 'Lucknow', icon: '🌤️' },
  { name: 'Hyderabad', icon: '🌦️' },{ name: 'Varanasi', icon: '🌊' },
  { name: 'Delhi', icon: '🌤️' },   { name: 'Jaipur', icon: '☀️' },
  { name: 'Kochi', icon: '🌧️' },   { name: 'Nagpur', icon: '🌤️' },
  { name: 'Goa', icon: '🏖️' },
]

function fmt(n, d = 1) {
  if (n == null || Number.isNaN(Number(n))) return '--'
  return Number(n).toFixed(d)
}

function WeatherCard({ icon, value, unit, label }) {
  return (
    <div style={{
      display: 'flex', flexDirection: 'column', alignItems: 'center',
      background: '#f8fafc', borderRadius: '12px',
      padding: '14px 10px', border: '1px solid #e2e8f0',
      flex: 1, minWidth: '80px',
    }}>
      <div style={{ fontSize: '1.4rem', marginBottom: '6px' }}>{icon}</div>
      <div style={{ fontSize: '1rem', fontWeight: 800, color: '#0f172a' }}>
        {value}<span style={{ fontSize: '0.68rem', color: '#64748b', marginLeft: '2px' }}>{unit}</span>
      </div>
      <div style={{ fontSize: '0.65rem', color: '#94a3b8', marginTop: '3px', textAlign: 'center', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
        {label}
      </div>
    </div>
  )
}

function RiskBar({ label, value, max = 100, color }) {
  const pct = Math.min(100, Math.max(0, (value / max) * 100))
  return (
    <div style={{ marginBottom: '10px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
        <span style={{ fontSize: '0.75rem', color: '#475569' }}>{label}</span>
        <span style={{ fontSize: '0.75rem', fontWeight: 700, color: '#0f172a' }}>{fmt(value, 2)}</span>
      </div>
      <div style={{ height: '5px', background: '#e2e8f0', borderRadius: '3px', overflow: 'hidden' }}>
        <div style={{
          height: '100%', width: `${pct}%`, background: color, borderRadius: '3px',
          transition: 'width 1s cubic-bezier(0.34,1.56,0.64,1)',
        }} />
      </div>
    </div>
  )
}

export default function CitySearch() {
  const [query, setQuery]     = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError]     = useState(null)
  const [result, setResult]   = useState(null)
  const inputRef              = useRef(null)

  async function lookup(name) {
    const city = (name || query).trim()
    if (!city) return
    setLoading(true); setError(null); setResult(null)
    try {
      setResult(await cityRisk(city))
    } catch (e) {
      setError(e?.message || `No data found for "${city}".`)
    } finally {
      setLoading(false)
    }
  }

  const c    = result ? (RISK_COLORS[result.risk_level] || RISK_COLORS.MODERATE) : null
  const cur  = result?.current_conditions
  const obs  = result?.observed_metrics
  const fc   = result?.forecast_metrics
  const comps = result?.risk_components || {}
  const riskPct = result ? Math.min(100, Math.max(0, result.predicted_risk)) : 0
  const R = 52, circ = 2 * Math.PI * R
  const dash = circ - (riskPct / 100) * circ

  return (
    <section className="section" id="city-search" style={{ scrollMarginTop: '80px' }}>
      <header className="section__head">
        <div>
          <h2 className="section__title">City Risk Lookup</h2>
          <p className="section__subtitle">
            Search any Indian city — live weather fetched from Open-Meteo, risk predicted instantly.
          </p>
        </div>
        <span style={{
          display: 'flex', alignItems: 'center', gap: '6px',
          fontSize: '0.75rem', fontWeight: 700, color: '#0d9488',
          background: 'rgba(13,148,136,0.1)', padding: '5px 14px',
          borderRadius: '20px', border: '1px solid rgba(13,148,136,0.25)',
        }}>
          <span style={{ width: 7, height: 7, borderRadius: '50%', background: '#0d9488', display: 'inline-block' }} />
          Live · Open-Meteo API
        </span>
      </header>

      <div className="section__body">

        {/* Search bar */}
        <form onSubmit={e => { e.preventDefault(); lookup() }}
          style={{ display: 'flex', gap: '10px', marginBottom: '14px' }}>
          <div style={{ position: 'relative', flex: 1 }}>
            <svg style={{ position: 'absolute', left: 14, top: '50%', transform: 'translateY(-50%)', color: '#64748b', pointerEvents: 'none' }}
              width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
            </svg>
            <input
              ref={inputRef} type="text" value={query}
              onChange={e => { setQuery(e.target.value); setError(null) }}
              placeholder="Mumbai, Patna, Surat, Guwahati, Delhi..."
              style={{
                width: '100%', boxSizing: 'border-box',
                padding: '11px 14px 11px 42px', fontSize: '0.95rem',
                border: '1.5px solid var(--border)', borderRadius: '10px',
                outline: 'none', fontFamily: 'inherit',
                background: 'var(--surface)', color: 'var(--text-primary)',
                transition: 'border-color 0.2s',
              }}
              onFocus={e => (e.target.style.borderColor = '#0d9488')}
              onBlur={e  => (e.target.style.borderColor = 'var(--border)')}
              aria-label="City name"
            />
          </div>
          <button type="submit" className="btn btn--primary"
            disabled={loading || !query.trim()}
            style={{ padding: '11px 26px', fontWeight: 700, fontSize: '0.92rem',
              minWidth: '130px', borderRadius: '10px', display: 'flex',
              alignItems: 'center', gap: '8px' }}>
            {loading ? (
              <>
                <svg style={{ animation: 'spin .9s linear infinite' }} width="15" height="15"
                  viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                  <path d="M21 12a9 9 0 1 1-6.219-8.56"/>
                </svg>
                Fetching...
              </>
            ) : (
              <>
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                  <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
                </svg>
                Predict Risk
              </>
            )}
          </button>
        </form>

        {/* Quick-city chips */}
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', marginBottom: '22px' }}>
          {QUICK_CITIES.map(({ name, icon }) => {
            const active = result?.city?.toLowerCase().startsWith(name.toLowerCase())
            return (
              <button key={name} type="button"
                onClick={() => { setQuery(name); lookup(name) }}
                disabled={loading}
                style={{
                  padding: '5px 13px', fontSize: '0.8rem', fontWeight: 600, cursor: 'pointer',
                  border: `1px solid ${active ? '#0d9488' : 'var(--border)'}`,
                  borderRadius: '20px', transition: 'all 0.15s',
                  background: active ? 'rgba(13,148,136,0.18)' : 'transparent',
                  color: active ? '#2dd4bf' : 'var(--text-secondary)',
                }}>
                {icon} {name}
              </button>
            )
          })}
        </div>

        {/* Error */}
        {error && (
          <div style={{
            background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)',
            color: '#fca5a5', borderRadius: '10px', padding: '12px 16px',
            marginBottom: '18px', fontSize: '0.88rem', display: 'flex', gap: '10px',
          }}>
            ⚠️ {error}
          </div>
        )}

        {/* Loading */}
        {loading && (
          <div style={{
            textAlign: 'center', padding: '40px 20px',
            background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: '16px',
          }}>
            <div style={{ fontSize: '2.5rem', marginBottom: '12px', animation: 'pulseOp 1.5s ease-in-out infinite' }}>🌐</div>
            <p style={{ color: '#64748b', fontSize: '0.88rem', margin: 0 }}>
              Geocoding → Fetching live weather → Running risk model...
            </p>
          </div>
        )}

        {/* Result card */}
        {result && c && !loading && (
          <div style={{
            background: '#fff', border: '1px solid #e2e8f0',
            borderRadius: '18px', overflow: 'hidden',
            boxShadow: `0 4px 24px ${c.glow}, 0 1px 4px rgba(0,0,0,0.06)`,
            animation: 'fadeUp 0.4s ease forwards',
          }}>

            {/* Header */}
            <div style={{
              padding: '22px 26px', borderBottom: '1px solid #e2e8f0',
              display: 'flex', justifyContent: 'space-between', alignItems: 'center',
              flexWrap: 'wrap', gap: '20px',
              background: 'linear-gradient(135deg,#f8fafc,#fff)',
            }}>
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
                  <h3 style={{ margin: 0, fontSize: '1.4rem', fontWeight: 900, color: '#0f172a' }}>
                    {result.city}
                  </h3>
                  <span style={{
                    padding: '3px 14px', borderRadius: '20px', fontWeight: 800,
                    fontSize: '0.8rem', background: c.grad, color: '#fff',
                    boxShadow: `0 2px 10px ${c.glow}`,
                  }}>{result.risk_level}</span>
                  {result.weather_live
                    ? <span style={{ fontSize: '0.73rem', fontWeight: 600, color: '#34d399', background: 'rgba(52,211,153,0.1)', padding: '3px 10px', borderRadius: '10px', border: '1px solid rgba(52,211,153,0.2)' }}>🛰️ Live Weather</span>
                    : <span style={{ fontSize: '0.73rem', fontWeight: 600, color: '#fbbf24', background: 'rgba(251,191,36,0.1)', padding: '3px 10px', borderRadius: '10px', border: '1px solid rgba(251,191,36,0.2)' }}>📊 IMD Seasonal</span>
                  }
                </div>
                <p style={{ margin: '6px 0 0', fontSize: '0.82rem', color: '#64748b' }}>
                  📍 {[result.state, result.country].filter(Boolean).join(', ')}
                  &nbsp;·&nbsp; {fmt(result.latitude, 4)}°N, {fmt(result.longitude, 4)}°E
                </p>
              </div>

              {/* Circular gauge */}
              <svg width="116" height="116" viewBox="0 0 120 120">
                <circle cx="60" cy="60" r={R} fill="none" stroke="#e2e8f0" strokeWidth="8"/>
                <defs>
                  <linearGradient id="rg" x1="0%" y1="0%" x2="100%" y2="0%">
                    <stop offset="0%" stopColor={c.badge}/>
                    <stop offset="100%" stopColor={c.bar}/>
                  </linearGradient>
                </defs>
                <circle cx="60" cy="60" r={R} fill="none"
                  stroke="url(#rg)" strokeWidth="8" strokeLinecap="round"
                  strokeDasharray={circ} strokeDashoffset={dash}
                  transform="rotate(-90 60 60)"
                  style={{ transition: 'stroke-dashoffset 1.2s cubic-bezier(0.34,1.56,0.64,1)', filter: `drop-shadow(0 0 5px ${c.badge})` }}
                />
                <text x="60" y="55" textAnchor="middle" fill="#0f172a" fontSize="20" fontWeight="900" fontFamily="inherit">
                  {fmt(result.predicted_risk, 1)}
                </text>
                <text x="60" y="68" textAnchor="middle" fill="#94a3b8" fontSize="8.5" fontFamily="inherit">RISK INDEX</text>
                <text x="60" y="80" textAnchor="middle" fill="#94a3b8" fontSize="8.5" fontFamily="inherit">/ 100</text>
              </svg>
            </div>

            {/* Weather cards */}
            {cur && (
              <div style={{ padding: '18px 26px', borderBottom: '1px solid #e2e8f0' }}>
                <div style={{ fontSize: '0.68rem', fontWeight: 700, color: '#64748b', textTransform: 'uppercase', letterSpacing: '1px', marginBottom: '12px' }}>Current Conditions</div>
                <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                  <WeatherCard icon="🌡️" value={fmt(cur.temperature_c, 1)}             unit="°C"  label="Temperature" />
                  <WeatherCard icon="💧" value={fmt(cur.relative_humidity_pct, 0)}       unit="%"   label="Humidity" />
                  <WeatherCard icon="💨" value={fmt(cur.wind_speed_kmh, 1)}              unit="km/h" label="Wind" />
                  <WeatherCard icon="🌧️" value={fmt(cur.current_precipitation_mm, 1)}   unit="mm"  label="Curr. Rain" />
                  <WeatherCard icon="📅" value={fmt(obs?.rainfall_last_24h, 1)}          unit="mm"  label="Past 24h" />
                  <WeatherCard icon="🔮" value={fmt(fc?.next_6h_precipitation_mm, 1)}    unit="mm"  label="Next 6h" />
                  <WeatherCard icon="📊" value={fmt(fc?.max_precip_probability_6h, 0)}   unit="%"   label="Precip Prob." />
                </div>
              </div>
            )}

            {/* Risk components */}
            {Object.keys(comps).length > 0 && (
              <div style={{ padding: '18px 26px', borderBottom: '1px solid #e2e8f0' }}>
                <div style={{ fontSize: '0.68rem', fontWeight: 700, color: '#64748b', textTransform: 'uppercase', letterSpacing: '1px', marginBottom: '14px' }}>Risk Component Breakdown</div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0 40px' }}>
                  {Object.entries(comps).map(([k, v]) => (
                    <RiskBar key={k}
                      label={k.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
                      value={v} max={k.includes('mm') ? 50 : k.includes('pct') ? 100 : k.includes('factor') || k.includes('index') ? 3 : 100}
                      color={c.bar} />
                  ))}
                </div>
              </div>
            )}

            {/* Explanation */}
            <div style={{ padding: '18px 26px', background: '#f8fafc' }}>
              <div style={{ fontSize: '0.68rem', fontWeight: 700, color: '#64748b', textTransform: 'uppercase', letterSpacing: '1px', marginBottom: '8px' }}>AI Risk Explanation</div>
              <p style={{ margin: '0 0 8px', fontSize: '0.87rem', color: '#334155', lineHeight: 1.7 }}>{result.explanation}</p>
              <p style={{ margin: 0, fontSize: '0.72rem', color: '#94a3b8' }}>
                🛰️ {result.weather_source}
                {result.data_timestamp
                  ? ` · ${new Date(result.data_timestamp).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata', hour: '2-digit', minute: '2-digit', day: 'numeric', month: 'short' })}`
                  : ''}
              </p>
            </div>
          </div>
        )}
      </div>

      <style>{`
        @keyframes fadeUp  { from { opacity:0; transform:translateY(14px); } to { opacity:1; transform:translateY(0); } }
        @keyframes spin    { to { transform:rotate(360deg); } }
        @keyframes pulseOp { 0%,100%{opacity:1} 50%{opacity:.4} }
      `}</style>
    </section>
  )
}

