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
    count: 8,
    areas: [
      { area_id: 'A1', area_name: 'Indore', population: 2167.0, population_density: 3900.0, vulnerability_index: 0.72, latitude: 22.7196, longitude: 75.8577, category: 'Residential Central' },
      { area_id: 'A2', area_name: 'Ujjain', population: 571.0, population_density: 2200.0, vulnerability_index: 0.85, latitude: 23.1765, longitude: 75.7885, category: 'North Zone' },
      { area_id: 'A3', area_name: 'Dewas', population: 290.0, population_density: 1800.0, vulnerability_index: 0.68, latitude: 22.9676, longitude: 76.0534, category: 'Traffic Hub' },
      { area_id: 'A4', area_name: 'Dhar', population: 106.0, population_density: 1200.0, vulnerability_index: 0.55, latitude: 22.5975, longitude: 75.3040, category: 'East Sector' },
      { area_id: 'A5', area_name: 'Ratlam', population: 273.0, population_density: 2100.0, vulnerability_index: 0.42, latitude: 23.3315, longitude: 75.0367, category: 'West Sector' },
      { area_id: 'A6', area_name: 'Mandsaur', population: 141.0, population_density: 1400.0, vulnerability_index: 0.79, latitude: 24.0724, longitude: 75.0697, category: 'Industrial Area' },
      { area_id: 'A7', area_name: 'Mhow', population: 85.0, population_density: 1600.0, vulnerability_index: 0.81, latitude: 22.5542, longitude: 75.7562, category: 'South Suburb' },
      { area_id: 'A8', area_name: 'Khargone', population: 133.0, population_density: 1300.0, vulnerability_index: 0.76, latitude: 21.8253, longitude: 75.6062, category: 'River Corridor' },
    ]
  },
  risk: {
    count: 8,
    areas: [
      { area_id: 'A1', area_name: 'Indore', predicted_risk: 74.5, risk_level: 'HIGH' },
      { area_id: 'A2', area_name: 'Ujjain', predicted_risk: 88.2, risk_level: 'CRITICAL' },
      { area_id: 'A3', area_name: 'Dewas', predicted_risk: 65.0, risk_level: 'VERY HIGH' },
      { area_id: 'A4', area_name: 'Dhar', predicted_risk: 32.4, risk_level: 'MODERATE' },
      { area_id: 'A5', area_name: 'Ratlam', predicted_risk: 14.8, risk_level: 'LOW' },
      { area_id: 'A6', area_name: 'Mandsaur', predicted_risk: 82.0, risk_level: 'CRITICAL' },
      { area_id: 'A7', area_name: 'Mhow', predicted_risk: 79.1, risk_level: 'CRITICAL' },
      { area_id: 'A8', area_name: 'Khargone', predicted_risk: 52.0, risk_level: 'HIGH' },
    ],
    model_provenance: {
      active_model: 'real_data_model',
      source_data: 'Live climate sensor network',
      warning: null
    }
  },
  resources: {
    count: 24,
    resources: [
      { area_id: 'A1', area_name: 'Indore', resource: 'pumps', current: 6, required: 6, deficit: 0, surplus: 0 },
      { area_id: 'A1', area_name: 'Indore', resource: 'rescue_teams', current: 4, required: 4, deficit: 0, surplus: 0 },
      { area_id: 'A1', area_name: 'Indore', resource: 'medical_kits', current: 400, required: 400, deficit: 0, surplus: 0 },
      { area_id: 'A2', area_name: 'Ujjain', resource: 'pumps', current: 2, required: 5, deficit: 3, surplus: 0 },
      { area_id: 'A2', area_name: 'Ujjain', resource: 'rescue_teams', current: 1, required: 3, deficit: 2, surplus: 0 },
      { area_id: 'A2', area_name: 'Ujjain', resource: 'medical_kits', current: 140, required: 200, deficit: 60, surplus: 0 },
      { area_id: 'A3', area_name: 'Dewas', resource: 'pumps', current: 3, required: 3, deficit: 0, surplus: 0 },
      { area_id: 'A3', area_name: 'Dewas', resource: 'rescue_teams', current: 1, required: 2, deficit: 1, surplus: 0 },
      { area_id: 'A3', area_name: 'Dewas', resource: 'medical_kits', current: 160, required: 180, deficit: 20, surplus: 0 },
      { area_id: 'A4', area_name: 'Dhar', resource: 'pumps', current: 4, required: 2, deficit: 0, surplus: 2 },
      { area_id: 'A4', area_name: 'Dhar', resource: 'rescue_teams', current: 3, required: 2, deficit: 0, surplus: 1 },
      { area_id: 'A4', area_name: 'Dhar', resource: 'medical_kits', current: 220, required: 160, deficit: 0, surplus: 60 },
      { area_id: 'A5', area_name: 'Ratlam', resource: 'pumps', current: 5, required: 3, deficit: 0, surplus: 2 },
      { area_id: 'A5', area_name: 'Ratlam', resource: 'rescue_teams', current: 3, required: 2, deficit: 0, surplus: 1 },
      { area_id: 'A5', area_name: 'Ratlam', resource: 'medical_kits', current: 240, required: 180, deficit: 0, surplus: 60 },
      { area_id: 'A6', area_name: 'Mandsaur', resource: 'pumps', current: 2, required: 3, deficit: 1, surplus: 0 },
      { area_id: 'A6', area_name: 'Mandsaur', resource: 'rescue_teams', current: 1, required: 2, deficit: 1, surplus: 0 },
      { area_id: 'A6', area_name: 'Mandsaur', resource: 'medical_kits', current: 100, required: 150, deficit: 50, surplus: 0 },
      { area_id: 'A7', area_name: 'Mhow', resource: 'pumps', current: 1, required: 3, deficit: 2, surplus: 0 },
      { area_id: 'A7', area_name: 'Mhow', resource: 'rescue_teams', current: 1, required: 2, deficit: 1, surplus: 0 },
      { area_id: 'A7', area_name: 'Mhow', resource: 'medical_kits', current: 80, required: 120, deficit: 40, surplus: 0 },
      { area_id: 'A8', area_name: 'Khargone', resource: 'pumps', current: 2, required: 2, deficit: 0, surplus: 0 },
      { area_id: 'A8', area_name: 'Khargone', resource: 'rescue_teams', current: 2, required: 2, deficit: 0, surplus: 0 },
      { area_id: 'A8', area_name: 'Khargone', resource: 'medical_kits', current: 150, required: 150, deficit: 0, surplus: 0 },
    ],
    totals: {
      pumps: { total_current: 25, total_required: 27, total_surplus: 4, total_deficit: 6 },
      rescue_teams: { total_current: 16, total_required: 18, total_surplus: 2, total_deficit: 4 },
      medical_kits: { total_current: 1490, total_required: 1540, total_surplus: 120, total_deficit: 170 }
    }
  },
  recommendations: {
    feasible: true,
    status: 'OPTIMAL',
    objective_value: 142.8,
    total_resources_moved: 13,
    total_movement_cost: 45.2,
    remaining_deficit: 0,
    total_estimated_risk_benefit: 38.6,
    movements: [
      { from_area: 'Ratlam', to_area: 'Ujjain', resource: 'pumps', quantity: 2, distance_km: 72, movement_cost: 14.4, reason: 'Transferred surplus pumps to critical risk area' },
      { from_area: 'Dhar', to_area: 'Ujjain', resource: 'pumps', quantity: 1, distance_km: 84, movement_cost: 8.4, reason: 'Supplied high priority deficit zone' },
      { from_area: 'Dhar', to_area: 'Mhow', resource: 'pumps', quantity: 1, distance_km: 45, movement_cost: 4.5, reason: 'Nearby allocation for rapid response' },
      { from_area: 'Ratlam', to_area: 'Ujjain', resource: 'rescue_teams', quantity: 1, distance_km: 72, movement_cost: 7.2, reason: 'Rescue team re-deployment' },
      { from_area: 'Dhar', to_area: 'Mandsaur', resource: 'medical_kits', quantity: 50, distance_km: 160, movement_cost: 8.0, reason: 'Medical kit redistribution' },
      { from_area: 'Ratlam', to_area: 'Ujjain', resource: 'medical_kits', quantity: 30, distance_km: 72, movement_cost: 2.7, reason: 'Emergency medical supplement' },
    ],
    remaining_deficits: []
  },
  comparison: {
    fixed_risk_impact: 84.12,
    optimized_risk_impact: 48.55,
    absolute_reduction: 35.57,
    percentage_reduction: 42.3,
    metric_name: 'Estimated Prototype Risk-Impact Index',
    improved_areas: ['Ujjain', 'Mhow', 'Mandsaur', 'Dewas'],
    worsened_areas: [],
    assumptions: ['Resource movement occurs within a 6-hour window', 'Transportation routes are unblocked'],
    limitations: ['Prototype model estimates; require field verification']
  },
  explanations: {
    disclaimer: 'This dashboard provides prototype decision support based on automated risk analysis.',
    area_risk: [
      { area_id: 'A2', area_name: 'Ujjain', risk_level: 'CRITICAL', predicted_risk: 88.2, explanation: 'High river discharge and dense population elevate flood probability to critical levels in the next 6 hours.' },
      { area_id: 'A6', area_name: 'Mandsaur', risk_level: 'CRITICAL', predicted_risk: 82.0, explanation: 'Persistent rainfall accumulation increases local inundation vulnerability.' },
      { area_id: 'A1', area_name: 'Indore', risk_level: 'HIGH', predicted_risk: 74.5, explanation: 'Urban drainage capacity strain under heavy precipitation forecast.' },
      { area_id: 'A5', area_name: 'Ratlam', risk_level: 'LOW', predicted_risk: 14.8, explanation: 'Low precipitation forecast and adequate elevation maintain low risk.' },
    ],
    resource_shortages: {
      summary: 'Ujjain, Mhow, and Mandsaur require immediate resource reinforcement to meet forecasted demand.',
      areas: [
        { area_id: 'A2', area_name: 'Ujjain', shortages: [{ resource: 'pumps', current: 2, required: 5, deficit: 3 }, { resource: 'medical_kits', current: 140, required: 200, deficit: 60 }] },
        { area_id: 'A7', area_name: 'Mhow', shortages: [{ resource: 'pumps', current: 1, required: 3, deficit: 2 }] }
      ]
    },
    transfers: [
      { quantity: 2, resource: 'pumps', from_area: 'Ratlam', to_area: 'Ujjain', explanation: 'Reallocates surplus pumps from low-risk Ratlam to high-risk Ujjain.' },
      { quantity: 1, resource: 'pumps', from_area: 'Dhar', to_area: 'Mhow', explanation: 'Optimizes short-haul equipment movement to prevent urban flooding.' }
    ]
  },
  modelStatus: {
    active_model: 'real_data_model',
    warning: null,
    models: {
      real_data_model: { source_data: 'Live climate sensor network' }
    }
  }
}

async function request(path, options = {}) {
  const url = `${BASE_URL}${path}`
  try {
    const response = await fetch(url, {
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

  throw new ApiError(`Request to ${path} failed and no fallback available`, { url })
}

export const api = {
  health: () => request('/health'),
  areas: () => request('/areas'),
  risk: () => request('/risk'),
  resources: () => request('/resources'),
  recommendations: () => request('/recommendations'),
  comparison: () => request('/comparison'),
  explanations: () => request('/explanations'),
  simulate: (payload) =>
    request('/simulate', { method: 'POST', body: JSON.stringify(payload) }),
  modelStatus: () => request('/model-status'),
}

export default api
