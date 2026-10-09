import { useMemo, useState } from 'react'
import { CircleMarker, MapContainer, Polyline, Popup, ScaleControl, TileLayer, Tooltip } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'
import { RISK_CATEGORIES, fmtInt, fmtNum, riskMeta } from '../format'
import { computeMapCenter, joinMapData, resolveTransferRoutes } from '../mapData'
import { Section } from './ui'

const RESOURCE_KEYS = ['pumps', 'rescue_teams', 'medical_kits']

function riskColor(level) {
  const key = String(level || '').toUpperCase()
  if (key === 'LOW') return '#10b981'
  if (key === 'MODERATE') return '#eab308'
  if (key === 'HIGH') return '#f97316'
  if (key === 'VERY HIGH') return '#ea580c'
  if (key === 'CRITICAL') return '#ef4444'
  return '#64748b'
}

function getWardIcon(index) {
  const icons = [
    // House / Residential
    <svg key="1" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" /><polyline points="9 22 9 12 15 12 15 22" /></svg>,
    // Factory / Industrial
    <svg key="2" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M2 20a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V8l-7 5V8l-7 5V4H2z" /></svg>,
    // Transport / Car
    <svg key="3" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="1" y="3" width="15" height="13" /><polygon points="16 8 20 8 23 11 23 16 16 16 16 8" /><circle cx="5.5" cy="18.5" r="2.5" /><circle cx="18.5" cy="18.5" r="2.5" /></svg>,
    // Building
    <svg key="4" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="4" y="2" width="16" height="20" rx="2" ry="2" /><line x1="9" y1="6" x2="9" y2="6.01" /><line x1="15" y1="6" x2="15" y2="6.01" /><line x1="9" y1="10" x2="9" y2="10.01" /><line x1="15" y1="10" x2="15" y2="10.01" /><line x1="9" y1="14" x2="9" y2="14.01" /><line x1="15" y1="14" x2="15" y2="14.01" /></svg>
  ]
  return icons[index % icons.length]
}

function AreaDetails({ area }) {
  if (!area) return <div className="risk-map__detail" style={{ color: '#64748b', fontSize: '0.85rem' }}>Select a map marker or ward on the right panel to inspect detailed flood risk &amp; resource parameters.</div>
  const meta = riskMeta(area.risk_level)
  return (
    <div className="risk-map__detail" aria-live="polite">
      <h3>{area.area_name}</h3>
      <p style={{ margin: '4px 0 8px' }}>
        <span className="muted">Predicted 6h risk:</span>{' '}
        {area.hasRiskData ? (
          <>
            <strong>{fmtNum(area.predicted_risk)} / 100</strong>{' '}
            <span className={`tag-badge tag-badge--${area.risk_level === 'CRITICAL' ? 'red' : area.risk_level.includes('HIGH') ? 'orange' : area.risk_level === 'MODERATE' ? 'yellow' : 'green'}`}>
              {meta.label}
            </span>
          </>
        ) : 'Risk data unavailable'}
      </p>
      {area.hasResourceData ? (
        <>
          <p className="muted" style={{ margin: '8px 0 4px', fontSize: '0.8rem', fontWeight: 700 }}>Resource Deficits</p>
          <ul style={{ margin: '0 0 8px', paddingLeft: '18px', fontSize: '0.85rem' }}>
            {RESOURCE_KEYS.map((key) => (
              <li key={key}>{key.replaceAll('_', ' ')}: <strong>{fmtInt(area.deficits[key] ?? 0)}</strong></li>
            ))}
          </ul>
          <p style={{ margin: 0, fontSize: '0.85rem' }}>Total Deficit: <strong>{fmtInt(area.totalDeficit)} units</strong></p>
        </>
      ) : <p className="muted" style={{ fontSize: '0.8rem' }}>Resource data unavailable</p>}
    </div>
  )
}

export default function RiskMap({ areas, risk, resources, recommendations, loading = false, error = null, onRetry }) {
  const joined = useMemo(() => joinMapData(areas, risk, resources), [areas, risk, resources])
  const routes = useMemo(() => resolveTransferRoutes(recommendations, areas), [recommendations, areas])
  const center = useMemo(() => computeMapCenter(joined.areas), [joined.areas])
  const [selectedId, setSelectedId] = useState(null)
  const [showRoutes, setShowRoutes] = useState(true)
  const [activeFilter, setActiveFilter] = useState('Live')
  const selectedArea = joined.areas.find((area) => String(area.area_id) === String(selectedId)) || null

  // Calculate summary metrics for the 4 stat cards (Matching Reference Image 2!)
  const totalMonitored = joined.areas.length
  const lowestRiskArea = useMemo(() => {
    if (!joined.areas.length) return null
    return [...joined.areas].sort((a, b) => (a.predicted_risk ?? 999) - (b.predicted_risk ?? 999))[0]
  }, [joined.areas])

  const highestRiskArea = useMemo(() => {
    if (!joined.areas.length) return null
    return [...joined.areas].sort((a, b) => (b.predicted_risk ?? 0) - (a.predicted_risk ?? 0))[0]
  }, [joined.areas])

  const totalDeficitSum = useMemo(() => {
    return joined.areas.reduce((acc, a) => acc + (a.totalDeficit || 0), 0)
  }, [joined.areas])

  return (
    <Section
      id="live-map"
      title="Ward-Wise Interactive Map"
      subtitle="Hyper-local decision making - Visual, easy for non-technical users"
      loading={loading}
      error={error}
      onRetry={onRetry}
      isEmpty={!joined.areas.length && !joined.excluded.length}
    >
      {/* Time & Category Filter Bar (Matching Reference Image 2!) */}
      <div className="filter-bar">
        <div className="filter-pills">
          {['Live', 'By Hour', 'By Day'].map((f) => (
            <button
              key={f}
              type="button"
              className={`filter-pill ${activeFilter === f ? 'is-active' : ''}`}
              onClick={() => setActiveFilter(f)}
            >
              {f}
            </button>
          ))}
        </div>
        <label style={{ fontSize: '0.84rem', color: '#475569', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '8px' }}>
          <input
            type="checkbox"
            checked={showRoutes}
            onChange={(e) => setShowRoutes(e.target.checked)}
            style={{ accentColor: '#0d9488', width: '16px', height: '16px' }}
          />
          Show transfer connections ({routes.length})
        </label>
      </div>

      {/* 4 Summary Stat Cards Grid (Matching Reference Image 2!) */}
      <div className="stat-grid">
        <div className="pill-card">
          <span className="pill-card__label">Monitored Areas</span>
          <div className="pill-card__content">
            <span className="tag-badge tag-badge--orange">
              {totalMonitored} Active Zones
            </span>
          </div>
        </div>

        <div className="pill-card">
          <span className="pill-card__label">Lowest Risk Zone</span>
          <div className="pill-card__content">
            <span className="tag-badge tag-badge--ok">
              {lowestRiskArea ? `${Math.round(lowestRiskArea.predicted_risk)} Risk` : 'N/A'}
            </span>
            <span style={{ fontSize: '0.88rem', fontWeight: 700, color: '#0f172a' }}>
              {lowestRiskArea?.area_name || 'N/A'}
            </span>
          </div>
        </div>

        <div className="pill-card">
          <span className="pill-card__label">Most Vulnerable</span>
          <div className="pill-card__content">
            <span className="tag-badge tag-badge--danger">
              {highestRiskArea ? `${Math.round(highestRiskArea.predicted_risk)} Risk` : 'N/A'}
            </span>
            <span style={{ fontSize: '0.88rem', fontWeight: 700, color: '#0f172a' }}>
              {highestRiskArea?.area_name || 'N/A'}
            </span>
          </div>
        </div>

        <div className="pill-card">
          <span className="pill-card__label">Total Resource Deficit</span>
          <div className="pill-card__content">
            <span className="pill-card__value">{totalDeficitSum}</span>
            <span className="muted" style={{ fontSize: '0.82rem' }}>units required</span>
          </div>
        </div>
      </div>

      {/* Main Map & Sidebar Layout (Matching Reference Image 2!) */}
      <div className="risk-map__layout">
        {/* Left Column: Interactive Map */}
        <div className="risk-map__map-wrap">
          {/* Top Left Overlay Badge inside map (Reference Image 2) */}
          <div className="risk-map__overlay-badge">
            <span className="status-dot" />
            <span>Live Risk Map</span>
          </div>

          <MapContainer
            center={center}
            zoom={7}
            scrollWheelZoom={false}
            className="risk-map__map"
            aria-label="Geographic flood risk map"
          >
            <TileLayer
              attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
              url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            />
            <ScaleControl position="bottomleft" />

            {joined.areas.map((area) => {
              const isSelected = String(selectedId) === String(area.area_id)
              const color = riskColor(area.risk_level)
              const riskVal = area.predicted_risk !== null ? Math.round(area.predicted_risk) : '--'

              return (
                <CircleMarker
                  key={area.area_id}
                  center={[area.latitude, area.longitude]}
                  radius={isSelected ? 14 : 10}
                  pathOptions={{
                    color: isSelected ? '#0f172a' : color,
                    fillColor: color,
                    fillOpacity: 0.85,
                    weight: isSelected ? 3 : 2,
                  }}
                  eventHandlers={{ click: () => setSelectedId(area.area_id) }}
                >
                  <Tooltip permanent direction="top" offset={[0, -10]} opacity={0.9}>
                    <span style={{ fontWeight: 800, color: '#0f172a' }}>
                      {area.area_name} ({riskVal})
                    </span>
                  </Tooltip>
                  <Popup>
                    <div style={{ padding: '4px' }}>
                      <strong style={{ fontSize: '1rem', color: '#0f172a' }}>{area.area_name}</strong><br />
                      <span>Predicted Risk: <strong>{fmtNum(area.predicted_risk)} ({area.risk_level})</strong></span><br />
                      <span>Total Deficit: <strong>{fmtInt(area.totalDeficit)} units</strong></span><br />
                      <button
                        type="button"
                        className="btn btn--primary"
                        style={{ marginTop: '8px', padding: '4px 12px', fontSize: '0.78rem' }}
                        onClick={() => setSelectedId(area.area_id)}
                      >
                        Inspect Ward Details
                      </button>
                    </div>
                  </Popup>
                </CircleMarker>
              )
            })}

            {showRoutes && routes.map((route, index) => (
              <Polyline
                key={`${route.from}-${route.to}-${route.resource}-${index}`}
                positions={[route.fromPos, route.toPos]}
                pathOptions={{ color: '#0d9488', weight: 2.5, opacity: 0.85, dashArray: '6 6' }}
              />
            ))}
          </MapContainer>

          {/* Bottom Left Legend inside Map Wrap (Reference Image 2) */}
          <div className="risk-map__legend" aria-label="Risk legend">
            <strong>Risk level:</strong>
            <span><i style={{ backgroundColor: '#10b981' }} /> Low (&lt;30)</span>
            <span><i style={{ backgroundColor: '#eab308' }} /> Moderate (30-60)</span>
            <span><i style={{ backgroundColor: '#f97316' }} /> High (60-80)</span>
            <span><i style={{ backgroundColor: '#ef4444' }} /> Critical (&gt;80)</span>
            {showRoutes && <span><i style={{ width: '16px', height: '0', borderRadius: '0', borderTop: '2px dashed #0d9488' }} /> Transfer route</span>}
          </div>
        </div>

        {/* Right Column: Ward Status Panel (Matching Reference Image 2!) */}
        <aside className="risk-map__sidebar">
          <div className="ward-status-head">
            <h3 className="ward-status-title">Ward Status</h3>
            <span className="muted" style={{ fontSize: '0.8rem' }}>{joined.areas.length} Wards</span>
          </div>

          <AreaDetails area={selectedArea} />

          <div className="risk-map__area-list">
            {joined.areas.map((area, idx) => {
              const isSelected = String(selectedId) === String(area.area_id)
              const score = area.predicted_risk !== null ? Math.round(area.predicted_risk) : 0
              const badgeTone = score > 80 ? 'danger' : score > 60 ? 'orange' : score > 30 ? 'warn' : 'ok'
              const icon = getWardIcon(idx)

              return (
                <button
                  key={area.area_id}
                  type="button"
                  className={`ward-card ${isSelected ? 'is-selected' : ''}`}
                  onClick={() => setSelectedId(area.area_id)}
                >
                  <div className="ward-card__left">
                    <div className="ward-card__icon">
                      {icon}
                    </div>
                    <div>
                      <h4 className="ward-card__title">{area.area_name}</h4>
                      <p className="ward-card__sub">{area.category || 'Monitored Ward'}</p>
                    </div>
                  </div>

                  <div className={`tag-badge tag-badge--${badgeTone}`}>
                    {score > 60 ? '⚠️' : '✓'} {score} Risk
                  </div>
                </button>
              )
            })}
          </div>
        </aside>
      </div>
    </Section>
  )
}
