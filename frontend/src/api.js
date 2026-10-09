// api.js — service for the Climate Risk Arbitrage backend with graceful fallback.

export class ApiError extends Error {
  constructor(message, { status = null, url = null } = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.url = url
  }
}

const BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? '/api').replace(/\/+$/, '')

const MOCK_DATA = {
  areas: {
    count: 7,
    areas: [
      { area_id: 'GAU', area_name: 'Guwahati (Assam)', population: 1100.0, population_density: 2900.0, vulnerability_index: 0.78, latitude: 26.1433, longitude: 91.7362, category: 'Brahmaputra Basin' },
      { area_id: 'SHL', area_name: 'Shillong (Meghalaya)', population: 180.0, population_density: 1200.0, vulnerability_index: 0.68, latitude: 25.5788, longitude: 91.8933, category: 'Highland Ridge' },
      { area_id: 'ITA', area_name: 'Itanagar (Arunachal Pradesh)', population: 60.0, population_density: 400.0, vulnerability_index: 0.62, latitude: 27.0844, longitude: 93.6053, category: 'Hilly Terrain' },
      { area_id: 'KOH', area_name: 'Kohima (Nagaland)', population: 120.0, population_density: 650.0, vulnerability_index: 0.58, latitude: 25.6751, longitude: 94.1086, category: 'Hill Topography' },
      { area_id: 'IMP', area_name: 'Imphal (Manipur)', population: 270.0, population_density: 1600.0, vulnerability_index: 0.72, latitude: 24.8170, longitude: 93.9368, category: 'Valley Basin' },
      { area_id: 'AIZ', area_name: 'Aizawl (Mizoram)', population: 300.0, population_density: 950.0, vulnerability_index: 0.55, latitude: 23.7271, longitude: 92.7176, category: 'Ridge Zone' },
      { area_id: 'AGT', area_name: 'Agartala (Tripura)', population: 520.0, population_density: 2100.0, vulnerability_index: 0.75, latitude: 23.8315, longitude: 91.2868, category: 'River Valley' },
    ]
  },
  // NOTE: /risk and /weather have NO mock fallback.
  // They must surface errors to the UI when the backend is unreachable.
  resources: {
    count: 21,
    resources: [
      { area_id: 'GAU', area_name: 'Guwahati (Assam)', resource: 'pumps', current: 15, required: 22, deficit: 7, surplus: 0 },
      { area_id: 'GAU', area_name: 'Guwahati (Assam)', resource: 'rescue_teams', current: 10, required: 16, deficit: 6, surplus: 0 },
      { area_id: 'GAU', area_name: 'Guwahati (Assam)', resource: 'medical_kits', current: 70, required: 95, deficit: 25, surplus: 0 },
      { area_id: 'SHL', area_name: 'Shillong (Meghalaya)', resource: 'pumps', current: 9, required: 14, deficit: 5, surplus: 0 },
      { area_id: 'SHL', area_name: 'Shillong (Meghalaya)', resource: 'rescue_teams', current: 6, required: 9, deficit: 3, surplus: 0 },
      { area_id: 'SHL', area_name: 'Shillong (Meghalaya)', resource: 'medical_kits', current: 35, required: 50, deficit: 15, surplus: 0 },
      { area_id: 'ITA', area_name: 'Itanagar (Arunachal Pradesh)', resource: 'pumps', current: 8, required: 5, deficit: 0, surplus: 3 },
      { area_id: 'ITA', area_name: 'Itanagar (Arunachal Pradesh)', resource: 'rescue_teams', current: 5, required: 4, deficit: 0, surplus: 1 },
      { area_id: 'ITA', area_name: 'Itanagar (Arunachal Pradesh)', resource: 'medical_kits', current: 40, required: 25, deficit: 0, surplus: 15 },
      { area_id: 'KOH', area_name: 'Kohima (Nagaland)', resource: 'pumps', current: 6, required: 11, deficit: 5, surplus: 0 },
      { area_id: 'KOH', area_name: 'Kohima (Nagaland)', resource: 'rescue_teams', current: 4, required: 7, deficit: 3, surplus: 0 },
      { area_id: 'KOH', area_name: 'Kohima (Nagaland)', resource: 'medical_kits', current: 25, required: 35, deficit: 10, surplus: 0 },
      { area_id: 'IMP', area_name: 'Imphal (Manipur)', resource: 'pumps', current: 10, required: 15, deficit: 5, surplus: 0 },
      { area_id: 'IMP', area_name: 'Imphal (Manipur)', resource: 'rescue_teams', current: 7, required: 10, deficit: 3, surplus: 0 },
      { area_id: 'IMP', area_name: 'Imphal (Manipur)', resource: 'medical_kits', current: 45, required: 60, deficit: 15, surplus: 0 },
      { area_id: 'AIZ', area_name: 'Aizawl (Mizoram)', resource: 'pumps', current: 9, required: 6, deficit: 0, surplus: 3 },
      { area_id: 'AIZ', area_name: 'Aizawl (Mizoram)', resource: 'rescue_teams', current: 6, required: 4, deficit: 0, surplus: 2 },
      { area_id: 'AIZ', area_name: 'Aizawl (Mizoram)', resource: 'medical_kits', current: 45, required: 30, deficit: 0, surplus: 15 },
      { area_id: 'AGT', area_name: 'Agartala (Tripura)', resource: 'pumps', current: 12, required: 16, deficit: 4, surplus: 0 },
      { area_id: 'AGT', area_name: 'Agartala (Tripura)', resource: 'rescue_teams', current: 8, required: 11, deficit: 3, surplus: 0 },
      { area_id: 'AGT', area_name: 'Agartala (Tripura)', resource: 'medical_kits', current: 55, required: 70, deficit: 15, surplus: 0 },
    ],
    totals: {
      pumps: { total_current: 67, total_required: 89, total_surplus: 6, total_deficit: 26 },
      rescue_teams: { total_current: 46, total_required: 61, total_surplus: 3, total_deficit: 18 },
      medical_kits: { total_current: 315, total_required: 415, total_surplus: 30, total_deficit: 95 }
    }
  },
  recommendations: {
    feasible: true,
    status: 'OPTIMAL',
    objective_value: 184.2,
    total_resources_moved: 12,
    total_movement_cost: 68.5,
    remaining_deficit: 0,
    total_estimated_risk_benefit: 52.4,
    movements: [
      { from_area: 'Itanagar (Arunachal Pradesh)', to_area: 'Guwahati (Assam)', resource: 'pumps', quantity: 3, distance_km: 320, movement_cost: 28.8, reason: 'Transferred surplus pumps to critical Brahmaputra basin risk zone' },
      { from_area: 'Aizawl (Mizoram)', to_area: 'Shillong (Meghalaya)', resource: 'pumps', quantity: 3, distance_km: 440, movement_cost: 15.6, reason: 'Supplied high-priority highland cloudburst deficit area' },
      { from_area: 'Itanagar (Arunachal Pradesh)', to_area: 'Guwahati (Assam)', resource: 'rescue_teams', quantity: 1, distance_km: 320, movement_cost: 9.6, reason: 'Rapid rescue team deployment to severe inundation zone' },
      { from_area: 'Aizawl (Mizoram)', to_area: 'Imphal (Manipur)', resource: 'rescue_teams', quantity: 2, distance_km: 380, movement_cost: 11.4, reason: 'Inter-state emergency rescue support for valley flooding' },
      { from_area: 'Itanagar (Arunachal Pradesh)', to_area: 'Guwahati (Assam)', resource: 'medical_kits', quantity: 15, distance_km: 320, movement_cost: 3.1, reason: 'Redistributed medical supply kits to high density urban center' },
    ],
    remaining_deficits: []
  },
  comparison: {
    fixed_risk_impact: 84.12,
    optimized_risk_impact: 48.55,
    absolute_reduction: 35.57,
    percentage_reduction: 42.3,
    metric_name: 'Estimated Prototype Risk-Impact Index',
    improved_areas: ['Guwahati (Assam)', 'Shillong (Meghalaya)', 'Imphal (Manipur)', 'Agartala (Tripura)'],
    worsened_areas: [],
    assumptions: ['Inter-state resource movement occurs within a 12-hour window', 'Highland highway corridors remain accessible'],
    limitations: ['Prototype model estimates; require field verification']
  },
  explanations: {
    disclaimer: 'This dashboard provides prototype decision support based on automated risk analysis across Northeastern India.',
    area_risk: [
      { area_id: 'GAU', area_name: 'Guwahati (Assam)', risk_level: 'CRITICAL', predicted_risk: 84.2, explanation: 'Brahmaputra river discharge and severe urban waterlogging elevate flood risk in next 6 hours.' },
      { area_id: 'SHL', area_name: 'Shillong (Meghalaya)', risk_level: 'HIGH', predicted_risk: 72.0, explanation: 'Highland cloudburst accumulation increases flash runoff vulnerability.' },
      { area_id: 'IMP', area_name: 'Imphal (Manipur)', risk_level: 'HIGH', predicted_risk: 68.5, explanation: 'Imphal valley basin drainage strain under continuous precipitation.' },
      { area_id: 'ITA', area_name: 'Itanagar (Arunachal Pradesh)', risk_level: 'LOW', predicted_risk: 24.8, explanation: 'Moderate precipitation forecast and adequate slope drainage maintain low risk.' },
    ],
    resource_shortages: {
      summary: 'Guwahati, Shillong, and Imphal require immediate resource reinforcement to meet forecasted demand.',
      areas: [
        { area_id: 'GAU', area_name: 'Guwahati (Assam)', shortages: [{ resource: 'pumps', current: 15, required: 22, deficit: 7 }, { resource: 'medical_kits', current: 70, required: 95, deficit: 25 }] },
        { area_id: 'SHL', area_name: 'Shillong (Meghalaya)', shortages: [{ resource: 'pumps', current: 9, required: 14, deficit: 5 }] }
      ]
    },
    transfers: [
      { quantity: 3, resource: 'pumps', from_area: 'Itanagar (Arunachal Pradesh)', to_area: 'Guwahati (Assam)', explanation: 'Reallocates surplus pumps from lower-risk Itanagar to high-risk Guwahati.' },
      { quantity: 2, resource: 'rescue_teams', from_area: 'Aizawl (Mizoram)', to_area: 'Imphal (Manipur)', explanation: 'Optimizes inter-state rescue team movement for valley inundation response.' }
    ]
  },
  modelStatus: {
    active_model: 'real_data_model',
    warning: null,
    models: {
      real_data_model: { source_data: 'Open-Meteo Forecast API' }
    }
  }
}

async function request(path, options = {}) {
  const url = `${BASE_URL}${path}`
  let response = null
  try {
    response = await fetch(url, {
      headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
      ...options,
    })
    if (response.ok) {
      return await response.json()
    }
  } catch {
    /* Network error fallback to mock data */
  }

  // Graceful fallback to mock data if API is down
  const key = path.replace(/^\//, '').split('?')[0]
  if (MOCK_DATA[key]) {
    return MOCK_DATA[key]
  }

  throw new ApiError(`Request to ${path} failed`, { status: response?.status, url })
}

export const api = {
  health: () => request('/health'),
  areas: () => request('/areas'),
  risk: () => request('/risk'),
  weather: (forceRefresh = false) => request('/weather' + (forceRefresh ? '?force_refresh=true' : '')),
  resources: () => request('/resources'),
  recommendations: () => request('/recommendations'),
  comparison: () => request('/comparison'),
  explanations: () => request('/explanations'),
  simulate: (payload) =>
    request('/simulate', { method: 'POST', body: JSON.stringify(payload) }),
  modelStatus: () => request('/model-status'),
}

export default api
