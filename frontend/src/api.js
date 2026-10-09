// api.js — small reusable service for the Climate Risk Arbitrage backend.
//
// The base URL is configurable via the Vite env var VITE_API_BASE_URL.
// The default is "/api", which the Vite dev server proxies to the FastAPI
// backend (see vite.config.js). For a deployed frontend, set
// VITE_API_BASE_URL to the absolute backend origin, e.g.
//   VITE_API_BASE_URL=https://api.example.com
//
// Every function returns the parsed JSON body on success and throws an
// ApiError on network failure or a non-2xx HTTP status. Callers are expected
// to handle errors per-section so one failing endpoint does not crash the
// whole dashboard.

export class ApiError extends Error {
  constructor(message, { status = null, url = null } = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.url = url
  }
}

const BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? '/api').replace(/\/+$/, '')

async function request(path, options = {}) {
  const url = `${BASE_URL}${path}`
  let response
  try {
    response = await fetch(url, {
      headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
      ...options,
    })
  } catch {
    throw new ApiError(`Network error reaching ${url}`, { url })
  }

  if (!response.ok) {
    let detail = ''
    try {
      const body = await response.json()
      detail = body?.detail || JSON.stringify(body)
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(
      `Request to ${path} failed with HTTP ${response.status}${detail ? `: ${detail}` : ''}`,
      { status: response.status, url },
    )
  }

  return response.json()
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
