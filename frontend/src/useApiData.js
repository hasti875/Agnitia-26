import { useCallback, useEffect, useRef, useState } from 'react'

const DEFAULT_REFRESH_MS = 10 * 60 * 1000 // 10 minutes

/**
 * useApiData(fn, { refreshInterval })
 *
 * Runs `fn` (an api.* call) once on mount, tracks loading / error / data,
 * and exposes a manual `reload`. Failures are captured in `error` and never
 * thrown, so a single failing endpoint only affects its own section.
 *
 * If `refreshInterval` is provided (ms), automatically re-fetches on that
 * interval and cleans up the timer when the component unmounts.
 */
export function useApiData(fn, { refreshInterval = null } = {}) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [updatedAt, setUpdatedAt] = useState(null)
  const seq = useRef(0)
  const timerRef = useRef(null)

  const load = useCallback(async () => {
    const id = ++seq.current
    setLoading(true)
    setError(null)
    try {
      const result = await fn()
      if (id === seq.current) {
        setData(result)
        setUpdatedAt(new Date())
      }
    } catch (err) {
      if (id === seq.current) {
        setError(err?.message || String(err))
        // Keep stale data visible rather than clearing on transient network error
      }
    } finally {
      if (id === seq.current) setLoading(false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Initial fetch
  useEffect(() => {
    load()
  }, [load])

  // Auto-refresh interval with proper cleanup
  useEffect(() => {
    if (!refreshInterval || refreshInterval <= 0) return
    timerRef.current = setInterval(() => {
      load()
    }, refreshInterval)
    return () => {
      if (timerRef.current) clearInterval(timerRef.current)
    }
  }, [load, refreshInterval])

  return { data, loading, error, updatedAt, reload: load }
}

export default useApiData
