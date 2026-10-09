import { useMemo, useState } from 'react'
import { CircleMarker, MapContainer, Polyline, Popup, ScaleControl, TileLayer, Tooltip } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'
import { RISK_CATEGORIES, fmtInt, fmtNum, riskMeta } from '../format'
import { computeMapCenter, joinMapData, resolveTransferRoutes } from '../mapData'
import { Section } from './ui'

const RESOURCE_KEYS = ['pumps', 'rescue_teams', 'medical_kits']

function riskColor(level) {
  const key = String(level || '').toUpperCase()
  if (key === 'LOW') return '#34d399'
  if (key === 'MODERATE') return '#a3e635'
  if (key === 'HIGH') return '#fbbf24'
  if (key === 'VERY HIGH') return '#fb923c'
  if (key === 'CRITICAL') return '#f87171'
  return '#94a3b8'
}

function AreaDetails({ area }) {
  if (!area) return <div className="risk-map__detail-empty">Select a map marker or area below to inspect its details.</div>
  const meta = riskMeta(area.risk_level)
  return (
    <div className="risk-map__detail" aria-live="polite">
      <h3>{area.area_name}</h3>
      <p><span className="muted">Predicted flood risk:</span> {area.hasRiskData ? <><strong>{fmtNum(area.predicted_risk)}</strong> <span className={`risk-badge risk-badge--${meta.level.toLowerCase().replace(/\s+/g, '-')}`}>{meta.label}</span></> : 'Risk data unavailable'}</p>
      {area.hasResourceData ? <>
        <p className="muted">Resource deficits</p>
        <ul className="risk-map__deficits">
          {RESOURCE_KEYS.map((key) => <li key={key}>{key.replaceAll('_', ' ')}: <strong>{fmtInt(area.deficits[key] ?? 0)}</strong></li>)}
        </ul>
        <p>Total listed deficit: <strong>{fmtInt(area.totalDeficit)}</strong></p>
      </> : <p className="risk-map__unavailable">Resource data unavailable</p>}
      <p className="footnote muted">Coordinates: {fmtNum(area.latitude, 4)}, {fmtNum(area.longitude, 4)}</p>
    </div>
  )
}

export default function RiskMap({ areas, risk, resources, recommendations, loading = false, error = null, onRetry }) {
  const joined = useMemo(() => joinMapData(areas, risk, resources), [areas, risk, resources])
  const routes = useMemo(() => resolveTransferRoutes(recommendations, areas), [recommendations, areas])
  const center = useMemo(() => computeMapCenter(joined.areas), [joined.areas])
  const [selectedId, setSelectedId] = useState(null)
  const [showRoutes, setShowRoutes] = useState(true)
  const [tileError, setTileError] = useState(false)
  const selectedArea = joined.areas.find((area) => String(area.area_id) === String(selectedId)) || null
  const recommendationsAvailable = Array.isArray(recommendations?.movements)

  return (
    <Section title="Geographic risk map" subtitle="Area-level synthetic risk estimates and illustrative resource transfers" loading={loading} error={error} onRetry={onRetry} isEmpty={!joined.areas.length && !joined.excluded.length}>
      <div className="risk-map__layout">
        <div className="risk-map__map-wrap">
          <MapContainer center={center} zoom={7} scrollWheelZoom={false} className="risk-map__map" aria-label="Geographic flood risk map">
            <TileLayer
              attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
              url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
              eventHandlers={{ tileerror: () => setTileError(true), load: () => setTileError(false) }}
            />
            <ScaleControl position="bottomleft" />
            {joined.areas.map((area) => <CircleMarker
              key={area.area_id}
              center={[area.latitude, area.longitude]}
              radius={selectedId === area.area_id ? 11 : 8}
              pathOptions={{ color: selectedId === area.area_id ? '#ffffff' : riskColor(area.risk_level), fillColor: riskColor(area.risk_level), fillOpacity: 0.88, weight: selectedId === area.area_id ? 3 : 2 }}
              eventHandlers={{ click: () => setSelectedId(area.area_id) }}
            >
              <Tooltip>{area.area_name} · {area.hasRiskData ? area.risk_level : 'Risk unavailable'}</Tooltip>
              <Popup>
                <strong>{area.area_name}</strong><br />
                Risk: {area.hasRiskData ? `${fmtNum(area.predicted_risk)} (${area.risk_level})` : 'Risk data unavailable'}<br />
                {area.hasResourceData ? `Total resource deficit: ${fmtInt(area.totalDeficit)}` : 'Resource data unavailable'}<br />
                <button type="button" onClick={() => setSelectedId(area.area_id)}>View details</button>
              </Popup>
            </CircleMarker>)}
            {showRoutes && routes.map((route, index) => <Polyline
              key={`${route.from}-${route.to}-${route.resource}-${index}`}
              positions={[route.fromPos, route.toPos]}
              pathOptions={{ color: '#e2e8f0', weight: 2, opacity: 0.9, dashArray: '7 7' }}
            />)}
          </MapContainer>
          {tileError ? <div className="risk-map__tile-warning" role="status">Map tiles could not load. Check your internet connection; area data remains available.</div> : null}
          <div className="risk-map__legend" aria-label="Risk legend">
            <strong>Risk level</strong>
            {RISK_CATEGORIES.map((category) => <span key={category.level}><i style={{ backgroundColor: riskColor(category.level) }} />{category.label}</span>)}
            <span><i className="risk-map__route-key" />Illustrative transfer</span>
          </div>
        </div>
        <aside className="risk-map__sidebar">
          <label className="risk-map__route-toggle"><input type="checkbox" checked={showRoutes} onChange={(event) => setShowRoutes(event.target.checked)} /> Show transfer connections</label>
          {!recommendationsAvailable ? <p className="risk-map__unavailable" role="status">Transfer data unavailable. Area markers and details remain available.</p> : <p className="footnote muted">{routes.length} illustrative connection{routes.length === 1 ? '' : 's'} shown when enabled.</p>}
          <p className="footnote muted">Dashed straight lines are illustrative connections, not road routes or executed transfers.</p>
          <AreaDetails area={selectedArea} />
          <h3 className="risk-map__list-title">Areas</h3>
          <ul className="risk-map__area-list">
            {joined.areas.map((area) => <li key={area.area_id}><button type="button" className={String(selectedId) === String(area.area_id) ? 'risk-map__area-button is-selected' : 'risk-map__area-button'} aria-label={`${area.area_name} ${area.hasRiskData ? area.risk_level : 'UNKNOWN'}`} onClick={() => setSelectedId(area.area_id)}><span className="risk-map__dot" style={{ backgroundColor: riskColor(area.risk_level) }} /> <span>{area.area_name}</span><small>{area.hasRiskData ? area.risk_level : 'UNKNOWN'}</small></button></li>)}
          </ul>
        </aside>
      </div>
      {joined.excluded.length > 0 ? <p className="footnote muted">Excluded {joined.excluded.length} area{joined.excluded.length === 1 ? '' : 's'} from the map because coordinates are invalid or use the (0, 0) null-island sentinel: {joined.excluded.map((area) => area.area_name).join(', ')}.</p> : null}
      <p className="footnote muted">This prototype uses synthetic data. Map markers and route lines are not official forecasts or operational guidance.</p>
    </Section>
  )
}
