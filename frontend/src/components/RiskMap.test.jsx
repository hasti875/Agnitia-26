import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { computeMapCenter, isValidCoord, joinMapData, resolveTransferRoutes } from '../mapData'
import RiskMap from './RiskMap'

vi.mock('react-leaflet', () => ({
  MapContainer: ({ children, center, scrollWheelZoom, ...props }) => <div data-testid="map" data-center={JSON.stringify(center)} data-scroll-wheel-zoom={String(Boolean(scrollWheelZoom))} {...props}>{children}</div>,
  TileLayer: (props) => <button type="button" data-testid="tile-layer" data-url={props.url} onClick={() => props.eventHandlers?.tileerror?.()}>tile layer</button>,
  ScaleControl: () => <div data-testid="scale-control" />,
  CircleMarker: ({ children, center, eventHandlers }) => <div data-testid="marker" data-center={JSON.stringify(center)} onClick={eventHandlers?.click}>{children}</div>,
  Tooltip: ({ children }) => <span>{children}</span>,
  Popup: ({ children }) => <div>{children}</div>,
  Polyline: ({ positions }) => <div data-testid="route" data-positions={JSON.stringify(positions)} />,
}))

const areasData = { areas: [
  { area_id: 1, area_name: 'Indore', latitude: 22.72, longitude: 75.86 },
  { area_id: 2, area_name: 'Dewas', latitude: 22.96, longitude: 76.06 },
] }
const riskData = { areas: [
  { area_id: 1, area_name: 'Indore', predicted_risk: 72, risk_level: 'HIGH' },
  { area_id: 2, area_name: 'Dewas', predicted_risk: 34, risk_level: 'MODERATE' },
] }
const resourcesData = { resources: [
  { area_id: 1, resource: 'pumps', deficit: 2 },
  { area_id: 1, resource: 'rescue_teams', deficit: 1 },
  { area_id: 1, resource: 'medical_kits', deficit: 3 },
] }
const recommendationsData = { movements: [{ from_area: 'Indore', to_area: 'Dewas', resource: 'pumps', quantity: 2 }] }

beforeEach(() => vi.clearAllMocks())

describe('map data helpers', () => {
  it('accepts ordinary valid coordinates', () => expect(isValidCoord(22.72, 75.86)).toBe(true))
  it('rejects non-number coordinates', () => expect(isValidCoord('22.7', 75.8)).toBe(false))
  it('rejects non-finite coordinates', () => expect(isValidCoord(Number.NaN, 10)).toBe(false))
  it('rejects out-of-range latitude', () => expect(isValidCoord(91, 10)).toBe(false))
  it('rejects out-of-range longitude', () => expect(isValidCoord(10, -181)).toBe(false))
  it('rejects null-island sentinel', () => expect(isValidCoord(0, 0)).toBe(false))
  it('joins risk and resources by area id', () => {
    const result = joinMapData(areasData, riskData, resourcesData)
    expect(result.areas[0]).toMatchObject({ area_name: 'Indore', predicted_risk: 72, totalDeficit: 6, hasResourceData: true })
  })
  it('marks missing risk as unknown without a fabricated score', () => {
    const result = joinMapData(areasData, { areas: [] }, resourcesData)
    expect(result.areas[0]).toMatchObject({ predicted_risk: null, risk_level: 'UNKNOWN', hasRiskData: false })
  })
  it('treats a null risk score as unavailable even if a label is present', () => {
    const result = joinMapData(areasData, { areas: [{ area_id: 1, predicted_risk: null, risk_level: 'HIGH' }] }, resourcesData)
    expect(result.areas[0]).toMatchObject({ predicted_risk: null, risk_level: 'UNKNOWN', hasRiskData: false })
  })
  it('marks missing resource data unavailable rather than a zero deficit', () => {
    const result = joinMapData(areasData, riskData, { resources: [] })
    expect(result.areas[0]).toMatchObject({ deficits: {}, totalDeficit: 0, hasResourceData: false })
  })
  it('excludes invalid coordinates and reports them separately', () => {
    const result = joinMapData({ areas: [...areasData.areas, { area_id: 3, area_name: 'Bad', latitude: 0, longitude: 0 }] }, riskData, resourcesData)
    expect(result.areas).toHaveLength(2)
    expect(result.excluded.map((area) => area.area_name)).toEqual(['Bad'])
  })
  it('resolves routes from area names to coordinates', () => {
    expect(resolveTransferRoutes(recommendationsData, areasData)[0]).toMatchObject({ from: 'Indore', to: 'Dewas', fromPos: [22.72, 75.86], toPos: [22.96, 76.06] })
  })
  it('skips routes whose endpoint name cannot be resolved', () => {
    expect(resolveTransferRoutes({ movements: [{ from_area: 'Missing', to_area: 'Dewas' }] }, areasData)).toEqual([])
  })
  it('skips routes whose endpoint coordinates are invalid', () => {
    const invalid = { areas: [{ ...areasData.areas[0], latitude: 0, longitude: 0 }, areasData.areas[1]] }
    expect(resolveTransferRoutes(recommendationsData, invalid)).toEqual([])
  })
  it('computes the mean of valid area coordinates', () => {
    const center = computeMapCenter(areasData.areas)
    expect(center[0]).toBeCloseTo(22.84)
    expect(center[1]).toBeCloseTo(75.96)
  })
  it('uses fallback center if there are no valid coordinates', () => expect(computeMapCenter([{ latitude: 0, longitude: 0 }])).toEqual([23, 75.9]))
})

describe('RiskMap component', () => {
  it('shows loading state', () => {
    render(<RiskMap loading areas={null} risk={null} resources={null} />)
    expect(screen.getByRole('status').textContent).toContain('Loading')
  })
  it('shows retry on map data error', () => {
    const retry = vi.fn()
    render(<RiskMap areas={null} risk={null} resources={null} error="API down" onRetry={retry} />)
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(retry).toHaveBeenCalledOnce()
  })
  it('shows empty state when no valid coordinate areas exist', () => render(<RiskMap areas={{ areas: [] }} risk={riskData} resources={resourcesData} />) && expect(screen.getByText('No data available.')).toBeTruthy())
  it('renders map markers and their coordinate positions', () => {
    render(<RiskMap areas={areasData} risk={riskData} resources={resourcesData} recommendations={recommendationsData} />)
    expect(screen.getAllByTestId('marker')).toHaveLength(2)
    expect(screen.getAllByTestId('marker')[0].dataset.center).toBe('[22.72,75.86]')
  })
  it('shows risk labels in marker tooltip and area list', () => {
    render(<RiskMap areas={areasData} risk={riskData} resources={resourcesData} />)
    expect(screen.getByText('Indore · HIGH')).toBeTruthy()
    expect(screen.getByText('MODERATE', { selector: 'small' })).toBeTruthy()
  })
  it('selects an area and shows its resource details', () => {
    render(<RiskMap areas={areasData} risk={riskData} resources={resourcesData} />)
    fireEvent.click(screen.getByRole('button', { name: /Indore HIGH/i }))
    expect(screen.getByText((content, element) => element?.tagName === 'P' && element.textContent === 'Total listed deficit: 6')).toBeTruthy()
  })
  it('displays unavailable resource text when resource rows are absent', () => {
    render(<RiskMap areas={areasData} risk={riskData} resources={{ resources: [] }} />)
    fireEvent.click(screen.getByRole('button', { name: /Indore HIGH/i }))
    expect(screen.getAllByText('Resource data unavailable').length).toBeGreaterThan(0)
  })
  it('renders routes when route toggle is enabled', () => {
    render(<RiskMap areas={areasData} risk={riskData} resources={resourcesData} recommendations={recommendationsData} />)
    expect(screen.getByTestId('route')).toBeTruthy()
  })
  it('hides routes when route toggle is disabled', () => {
    render(<RiskMap areas={areasData} risk={riskData} resources={resourcesData} recommendations={recommendationsData} />)
    fireEvent.click(screen.getByLabelText('Show transfer connections'))
    expect(screen.queryByTestId('route')).toBeNull()
  })
  it('keeps valid markers visible when recommendations are unavailable', () => {
    render(<RiskMap areas={areasData} risk={riskData} resources={resourcesData} recommendations={null} />)
    expect(screen.getAllByTestId('marker')).toHaveLength(2)
    expect(screen.getByText(/Transfer data unavailable/)).toBeTruthy()
  })
  it('documents excluded areas including the null-island sentinel', () => {
    const withBad = { areas: [...areasData.areas, { area_id: 3, area_name: 'Unknown place', latitude: 0, longitude: 0 }] }
    render(<RiskMap areas={withBad} risk={riskData} resources={resourcesData} />)
    expect(screen.getByText(/Excluded 1 area.*Unknown place/)).toBeTruthy()
  })
  it('shows a non-blocking warning when map tiles fail', () => {
    render(<RiskMap areas={areasData} risk={riskData} resources={resourcesData} />)
    fireEvent.click(screen.getByTestId('tile-layer'))
    expect(screen.getByText(/Map tiles could not load/)).toBeTruthy()
    expect(screen.getAllByTestId('marker')).toHaveLength(2)
  })
  it('includes the straight-line route disclaimer', () => {
    render(<RiskMap areas={areasData} risk={riskData} resources={resourcesData} recommendations={recommendationsData} />)
    expect(screen.getByText(/not road routes or executed transfers/)).toBeTruthy()
  })
})
