export const FALLBACK_CENTER = [25.6, 92.5]

export function isValidCoord(lat, lng) {
  return typeof lat === 'number' && Number.isFinite(lat)
    && typeof lng === 'number' && Number.isFinite(lng)
    && lat >= -90 && lat <= 90 && lng >= -180 && lng <= 180
    && !(lat === 0 && lng === 0)
}

function rowsOf(data, key) {
  const rows = data?.[key]
  return Array.isArray(rows) ? rows : []
}

export function joinMapData(areasData, riskData, resourcesData, weatherData) {
  const riskById = new Map(rowsOf(riskData, 'areas').map((row) => [String(row.area_id), row]))
  const resourceRows = rowsOf(resourcesData, 'resources')
  const resourcesById = new Map()
  for (const row of resourceRows) {
    const id = String(row.area_id)
    if (!resourcesById.has(id)) resourcesById.set(id, [])
    resourcesById.get(id).push(row)
  }

  const weatherRows = rowsOf(weatherData, 'areas')
  const weatherById = new Map()
  for (const row of weatherRows) {
    if (row.area_id) weatherById.set(String(row.area_id), row)
    if (row.area_name) weatherById.set(String(row.area_name).toLowerCase(), row)
  }

  const areas = rowsOf(areasData, 'areas').map((area) => {
    const id = String(area.area_id)
    const nameKey = String(area.area_name || '').toLowerCase()
    const riskRow = riskById.get(id)
    const weatherRow = weatherById.get(id) || weatherById.get(nameKey) || null
    const resourceList = resourcesById.get(id) || []
    const hasResourceData = resourceList.length > 0
    const deficits = {}
    for (const row of resourceList) {
      const key = String(row.resource || '').toLowerCase().replace(/[ -]+/g, '_')
      deficits[key] = Number.isFinite(Number(row.deficit)) ? Number(row.deficit) : 0
    }
    const lat = area.latitude
    const lng = area.longitude
    const coordsValid = isValidCoord(lat, lng)
    const predictedRisk = riskRow && riskRow.predicted_risk !== null && riskRow.predicted_risk !== undefined && Number.isFinite(Number(riskRow.predicted_risk))
      ? Number(riskRow.predicted_risk) : null

    return {
      area_id: area.area_id,
      area_name: area.area_name,
      latitude: lat,
      longitude: lng,
      coordsValid,
      predicted_risk: predictedRisk,
      risk_level: predictedRisk !== null ? (riskRow?.risk_level || 'UNKNOWN') : 'UNKNOWN',
      hasRiskData: Boolean(riskRow && predictedRisk !== null),
      deficits,
      totalDeficit: hasResourceData ? Object.values(deficits).reduce((sum, value) => sum + value, 0) : 0,
      hasResourceData,
      // Weather telemetry attributes
      weather: weatherRow,
      current_conditions: weatherRow?.current_conditions || null,
      observed_metrics: weatherRow?.observed_metrics || null,
      forecast_metrics: weatherRow?.forecast_metrics || null,
      weather_status: weatherRow?.status || (weatherRow ? 'ok' : 'unavailable'),
      is_stale: Boolean(weatherRow?.is_stale),
      weather_source: weatherRow?.source || 'Open-Meteo Forecast API',
      last_successful_fetch: weatherRow?.last_successful_fetch || null,
      data_timestamp: weatherRow?.data_timestamp || null,
    }
  })
  return { areas: areas.filter((area) => area.coordsValid), excluded: areas.filter((area) => !area.coordsValid) }
}

export function resolveTransferRoutes(recommendationsData, areasData) {
  const nameToArea = new Map(rowsOf(areasData, 'areas').map((area) => [String(area.area_name).trim().toLowerCase(), area]))
  return rowsOf(recommendationsData, 'movements').flatMap((movement) => {
    const from = nameToArea.get(String(movement.from_area || '').trim().toLowerCase())
    const to = nameToArea.get(String(movement.to_area || '').trim().toLowerCase())
    if (!from || !to || !isValidCoord(from.latitude, from.longitude) || !isValidCoord(to.latitude, to.longitude)) return []
    return [{
      from: from.area_name,
      to: to.area_name,
      resource: movement.resource,
      quantity: movement.quantity,
      fromPos: [from.latitude, from.longitude],
      toPos: [to.latitude, to.longitude],
    }]
  })
}

export function computeMapCenter(areas) {
  const valid = (Array.isArray(areas) ? areas : []).filter((area) => isValidCoord(area.latitude, area.longitude))
  if (!valid.length) return FALLBACK_CENTER
  return [
    valid.reduce((sum, area) => sum + area.latitude, 0) / valid.length,
    valid.reduce((sum, area) => sum + area.longitude, 0) / valid.length,
  ]
}
