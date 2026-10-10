import { useMemo, useState, useRef, useEffect } from 'react'
import { CircleMarker, LayerGroup, LayersControl, MapContainer, Polyline, Popup, ScaleControl, TileLayer, Tooltip, useMap } from 'react-leaflet'
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

function AreaDetails({ area, weatherInfo }) {
  if (!area) return <div className="risk-map__detail" style={{ color: '#64748b', fontSize: '0.85rem' }}>Select a map marker or ward on the right panel to inspect detailed flood risk &amp; resource parameters.</div>
  const meta = riskMeta(area.risk_level)

  const obs = weatherInfo?.observed_metrics
  const fc = weatherInfo?.forecast_metrics
  const curr = weatherInfo?.current_conditions
  const isStale = weatherInfo?.is_stale
  const isError = weatherInfo?.status === 'error'
  const isEstimated = weatherInfo?.status === 'estimated'

  return (
    <div className="risk-map__detail" aria-live="polite">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <h3 style={{ margin: 0 }}>{area.area_name}</h3>
          <span style={{ fontSize: '0.75rem', color: '#64748b' }}>
            Coord: {area.latitude.toFixed(2)}°N, {area.longitude.toFixed(2)}°E
          </span>
        </div>
        {weatherInfo && (
          <span className={`tag-badge ${isError ? 'tag-badge--red' : isStale ? 'tag-badge--yellow' : isEstimated ? 'tag-badge--orange' : 'tag-badge--teal'}`}>
            {isError ? '⚠️ Weather Offline' : isStale ? '⏱️ Stale Telemetry' : isEstimated ? '📊 IMD Seasonal Est.' : '🛰️ Open-Meteo Live'}
          </span>
        )}
      </div>

      <p style={{ margin: '8px 0 8px' }}>
        <span className="muted">Predicted Risk Index:</span>{' '}
        {area.hasRiskData ? (
          <>
            <strong>{fmtNum(area.predicted_risk)} / 100</strong>{' '}
            <span className={`tag-badge tag-badge--${area.risk_level === 'CRITICAL' ? 'red' : area.risk_level.includes('HIGH') ? 'orange' : area.risk_level === 'MODERATE' ? 'yellow' : 'green'}`}>
              {meta.label}
            </span>
            <div style={{ fontSize: '0.7rem', color: '#94a3b8', fontStyle: 'italic', marginTop: '2px' }}>
              *Live weather-driven risk score via Open-Meteo telemetry
            </div>
          </>
        ) : 'Risk data unavailable'}
      </p>

      {/* Live Weather Telemetry Section */}
      {weatherInfo && !isError && (
        <div style={{ background: '#f8fafc', borderRadius: '10px', padding: '10px 12px', margin: '8px 0', border: '1px solid #e2e8f0' }}>
          <div style={{ fontSize: '0.78rem', fontWeight: 700, color: isEstimated ? '#d97706' : '#0d9488', textTransform: 'uppercase', letterSpacing: '0.4px', marginBottom: '6px' }}>
            {isEstimated ? '📊 Weather Estimate (IMD Climatological Normals)' : 'Observed Telemetry (Open-Meteo)'}
          </div>
          {isEstimated && (
            <div style={{ fontSize: '0.72rem', color: '#92400e', background: '#fef3c7', borderRadius: '5px', padding: '4px 8px', marginBottom: '6px' }}>
              Live API rate-limited — showing IMD monthly climatological estimates for this region.
            </div>
          )}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '6px', fontSize: '0.8rem' }}>
            <div>Temp: <strong>{curr?.temperature_c ?? '--'}°C</strong></div>
            <div>Humidity: <strong>{curr?.relative_humidity_pct ?? '--'}%</strong></div>
            <div>Rain (Past 1h): <strong>{obs?.rainfall_last_1h ?? 0} mm</strong></div>
            <div>Rain (Past 6h): <strong>{obs?.rainfall_last_6h ?? 0} mm</strong></div>
            <div>Rain (Past 24h): <strong>{obs?.rainfall_last_24h ?? 0} mm</strong></div>
            <div>Soil Moisture: <strong>{obs?.soil_moisture_0_to_1cm ?? '--'}</strong></div>
          </div>

          <div style={{ fontSize: '0.78rem', fontWeight: 700, color: '#334155', textTransform: 'uppercase', letterSpacing: '0.4px', marginTop: '10px', marginBottom: '4px' }}>
            Upcoming Weather Forecast (Separated)
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '6px', fontSize: '0.8rem', color: '#475569' }}>
            <div>Next 6h Rain: <strong>{fc?.next_6h_precipitation_mm ?? 0} mm</strong></div>
            <div>Precip Prob: <strong>{fc?.max_precip_probability_6h ?? 0}%</strong></div>
          </div>

          {weatherInfo.last_successful_fetch && (
            <div style={{ fontSize: '0.7rem', color: '#94a3b8', marginTop: '6px' }}>
              Last Fetch: {new Date(weatherInfo.last_successful_fetch).toLocaleTimeString()} &middot; Source: {weatherInfo.source}
            </div>
          )}
        </div>
      )}

      {isError && (
        <div style={{ background: '#fee2e2', color: '#b91c1c', borderRadius: '8px', padding: '8px 10px', margin: '8px 0', fontSize: '0.78rem' }}>
          ⚠️ {weatherInfo.error_message || 'Failed to fetch live weather telemetry. No fabricated values shown.'}
        </div>
      )}

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

function MapFlyTo({ selectedArea }) {
  const map = useMap()
  useEffect(() => {
    if (selectedArea && selectedArea.latitude && selectedArea.longitude) {
      map.flyTo([selectedArea.latitude, selectedArea.longitude], 10, { duration: 1.2 })
    }
  }, [selectedArea, map])
  return null
}


export default function RiskMap({ areas, risk, resources, recommendations, weather, loading = false, error = null, onRetry }) {
  const joined = useMemo(() => joinMapData(areas, risk, resources, weather), [areas, risk, resources, weather])
  const routes = useMemo(() => resolveTransferRoutes(recommendations, areas), [recommendations, areas])
  const center = useMemo(() => computeMapCenter(joined.areas), [joined.areas])
  const [selectedId, setSelectedId] = useState(null)
  const [showRoutes, setShowRoutes] = useState(true)
  const [activeFilter, setActiveFilter] = useState('Live')
  const [searchTerm, setSearchTerm] = useState('')
  const markerRefs = useRef({})

  const selectedArea = joined.areas.find((area) => String(area.area_id) === String(selectedId)) || null

  const handleSearch = (e) => {
    e.preventDefault()
    const term = searchTerm.trim().toLowerCase()

    // Hardcoded Seven Sisters Capital Pincodes to area IDs map for problem statement demo
    const PINCODES = {
      '781001': 'GAU', // Guwahati
      '793001': 'SHL', // Shillong
      '791111': 'ITA', // Itanagar
      '797001': 'KOH', // Kohima
      '795001': 'IMP', // Imphal
      '796001': 'AIZ', // Aizawl
      '799001': 'AGT'  // Agartala
    }

    const matchedArea = joined.areas.find(a =>
      String(a.area_id) === PINCODES[term] ||
      a.area_name.toLowerCase().includes(term)
    )

    if (matchedArea) {
      setSelectedId(matchedArea.area_id)
      setSearchTerm('')
      markerRefs.current[matchedArea.area_id]?.openPopup()
    } else {
      alert("No matching city or pincode found in monitored zones.")
    }
  }


  const weatherMap = useMemo(() => {
    if (!weather?.areas) return {}
    const map = {}
    weather.areas.forEach((item) => {
      map[String(item.area_id)] = item
      map[String(item.area_name).toLowerCase()] = item
    })
    return map
  }, [weather])

  const selectedWeather = selectedArea ? (weatherMap[String(selectedArea.area_id)] || weatherMap[String(selectedArea.area_name).toLowerCase()]) : null

  // Check if any area has stale weather
  const hasStaleWeather = useMemo(() => {
    return joined.areas.some((a) => a.is_stale || a.weather_status === 'stale')
  }, [joined.areas])

  // Check if using IMD seasonal estimates (Open-Meteo offline)
  const hasEstimatedWeather = useMemo(() => {
    return !hasStaleWeather && joined.areas.some((a) => a.weather_status === 'estimated')
  }, [joined.areas, hasStaleWeather])

  // Calculate summary metrics for stat cards
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
      subtitle="Hyper-local decision making - Real-time backend risk & Open-Meteo weather telemetry"
      loading={loading}
      error={error}
      onRetry={onRetry}
      isEmpty={!joined.areas.length && !joined.excluded.length}
    >
      {/* Time & Refresh Control Bar */}
      <div className="filter-bar" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
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

        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          <form onSubmit={handleSearch} style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
            <input
              type="text"
              placeholder="Search by Pincode..."
              value={searchTerm}
              onChange={e => setSearchTerm(e.target.value)}
              style={{ fontSize: '0.8rem', padding: '5px 8px', borderRadius: '5px', border: '1px solid #cbd5e1', outline: 'none' }}
            />
            <button type="submit" className="btn btn--primary" style={{ padding: '5px 10px', fontSize: '0.8rem', borderRadius: '5px' }}>Search</button>
          </form>
          <button
            type="button"
            className="btn btn--outline"
            style={{ fontSize: '0.8rem', padding: '6px 14px', display: 'flex', alignItems: 'center', gap: '6px' }}
            onClick={onRetry}
            title="Force refresh live weather telemetry and backend predictions"
          >
            🔄 Refresh Telemetry
          </button>
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
      </div>

      {/* Stale Telemetry Warning Banner */}
      {hasStaleWeather && (
        <div style={{ background: '#fef3c7', border: '1px solid #f59e0b', color: '#92400e', borderRadius: '8px', padding: '8px 14px', margin: '8px 0', fontSize: '0.82rem', fontWeight: 600 }}>
          ⏱️ Notice: Displaying cached/stale weather telemetry from Open-Meteo. Click "Refresh Telemetry" to update live data.
        </div>
      )}

      {/* IMD Seasonal Estimate Banner */}
      {hasEstimatedWeather && (
        <div style={{ background: '#fff7ed', border: '1px solid #f97316', color: '#7c2d12', borderRadius: '8px', padding: '8px 14px', margin: '8px 0', fontSize: '0.82rem', fontWeight: 600 }}>
          📊 Open-Meteo daily API limit reached — showing IMD climatological estimates. Live weather resumes tomorrow. Risk scores use ML model fallback.
        </div>
      )}

      {/* 4 Summary Stat Cards Grid */}
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

      {/* Main Map & Sidebar Layout */}
      <div className="risk-map__layout">
        {/* Left Column: Interactive Map */}
        <div className="risk-map__map-wrap">
          {/* Top Left Overlay Badge inside map */}
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
            <MapFlyTo selectedArea={selectedArea} />
            <ScaleControl position="bottomleft" />

            <LayersControl position="topright">
              <LayersControl.BaseLayer checked name="OpenStreetMap Standard">
                <TileLayer
                  attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
                  url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
                />
              </LayersControl.BaseLayer>

              <LayersControl.Overlay checked name="Regional Flood Risk Markers">
                <LayerGroup>
                  {joined.areas.map((area) => {
                    const isSelected = String(selectedId) === String(area.area_id)
                    const color = riskColor(area.risk_level)
                    const riskVal = area.predicted_risk !== null ? Math.round(area.predicted_risk) : '--'
                    const obs = area.observed_metrics
                    const fc = area.forecast_metrics

                    return (
                      <CircleMarker
                        key={area.area_id}
                        ref={(r) => { if (r) markerRefs.current[area.area_id] = r }}
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
                          <div style={{ padding: '6px', maxWidth: '240px' }}>
                            <strong style={{ fontSize: '1rem', color: '#0f172a' }}>{area.area_name}</strong>
                            <div style={{ fontSize: '0.75rem', color: '#64748b', marginBottom: '6px' }}>
                              Lat: {area.latitude.toFixed(2)}°N, Lon: {area.longitude.toFixed(2)}°E
                            </div>

                            <div style={{ margin: '4px 0 6px', fontSize: '0.85rem' }}>
                              Live Risk Score: <strong>{fmtNum(area.predicted_risk)} ({area.risk_level})</strong>
                            </div>

                            <div style={{ fontSize: '0.78rem', background: '#f1f5f9', borderRadius: '6px', padding: '6px', margin: '6px 0' }}>
                              <div style={{ fontWeight: 700, color: '#0d9488' }}>Observed Weather</div>
                              <div>Rain 1h: <strong>{obs?.rainfall_last_1h ?? 0} mm</strong></div>
                              <div>Rain 6h: <strong>{obs?.rainfall_last_6h ?? 0} mm</strong></div>
                              <div>Rain 24h: <strong>{obs?.rainfall_last_24h ?? 0} mm</strong></div>
                              <div style={{ fontWeight: 700, color: '#334155', marginTop: '4px' }}>Upcoming Forecast</div>
                              <div>Forecast 6h Rain: <strong>{fc?.next_6h_precipitation_mm ?? 0} mm</strong></div>
                            </div>

                            <div style={{ fontSize: '0.7rem', color: '#64748b', marginBottom: '8px' }}>
                              Source: {area.weather_source}<br />
                              Status: {area.is_stale ? '⏱️ Stale' : area.weather_status === 'error' ? '⚠️ Offline' : area.weather_status === 'estimated' ? '📊 IMD Estimate' : '🟢 Live'}
                            </div>

                            <button
                              type="button"
                              className="btn btn--primary"
                              style={{ width: '100%', padding: '4px 12px', fontSize: '0.78rem' }}
                              onClick={() => setSelectedId(area.area_id)}
                            >
                              Inspect Ward Details
                            </button>
                          </div>
                        </Popup>
                      </CircleMarker>
                    )
                  })}
                </LayerGroup>
              </LayersControl.Overlay>

              {routes.length > 0 && (
                <LayersControl.Overlay checked={showRoutes} name={`Resource Routes (${routes.length})`}>
                  <LayerGroup>
                    {routes.map((route, index) => (
                      <Polyline
                        key={`${route.from}-${route.to}-${route.resource}-${index}`}
                        positions={[route.fromPos, route.toPos]}
                        pathOptions={{ color: '#0d9488', weight: 2.5, opacity: 0.85, dashArray: '6 6' }}
                      />
                    ))}
                  </LayerGroup>
                </LayersControl.Overlay>
              )}
            </LayersControl>
          </MapContainer>

          {/* Bottom Left Legend inside Map Wrap */}
          <div className="risk-map__legend" aria-label="Risk legend">
            <strong>Risk level:</strong>
            <span><i style={{ backgroundColor: '#10b981' }} /> Low (&lt;30)</span>
            <span><i style={{ backgroundColor: '#eab308' }} /> Moderate (30-60)</span>
            <span><i style={{ backgroundColor: '#f97316' }} /> High (60-80)</span>
            <span><i style={{ backgroundColor: '#ef4444' }} /> Critical (&gt;80)</span>
            {showRoutes && <span><i style={{ width: '16px', height: '0', borderRadius: '0', borderTop: '2px dashed #0d9488' }} /> Transfer route</span>}
          </div>
        </div>

        {/* Right Column: Ward Status Panel */}
        <aside className="risk-map__sidebar">
          <div className="ward-status-head">
            <h3 className="ward-status-title">Ward Status</h3>
            <span className="muted" style={{ fontSize: '0.8rem' }}>{joined.areas.length} Wards</span>
          </div>

          <AreaDetails area={selectedArea} weatherInfo={selectedWeather} />

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
