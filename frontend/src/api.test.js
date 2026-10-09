import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import api from './api'

// --- api.js: error handling & base URL -------------------------------------
describe('api service', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('throws ApiError with status on a non-2xx response', async () => {
    fetch.mockResolvedValueOnce({
      ok: false,
      status: 404,
      json: async () => ({ detail: 'not found' }),
    })
    await expect(api.health()).rejects.toMatchObject({ name: 'ApiError', status: 404 })
  })

  it('throws ApiError on a network failure', async () => {
    fetch.mockRejectedValueOnce(new TypeError('failed to fetch'))
    await expect(api.risk()).rejects.toMatchObject({ name: 'ApiError' })
  })

  it('returns parsed JSON on success', async () => {
    fetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => ({ status: 'ok' }),
    })
    await expect(api.health()).resolves.toEqual({ status: 'ok' })
  })

  it('sends POST body for simulate', async () => {
    fetch.mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({}) })
    await api.simulate({ rainfall_change_pct: 30 })
    const [, opts] = fetch.mock.calls[0]
    expect(opts.method).toBe('POST')
    expect(JSON.parse(opts.body)).toEqual({ rainfall_change_pct: 30 })
  })
})
