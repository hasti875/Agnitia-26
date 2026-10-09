import { useCallback, useEffect, useRef, useState } from 'react'

// useApiData(fn, deps)
// Runs `fn` (an api.* call) once on mount, tracks loading / error / data,
// and exposes a manual `reload`. Failures are captured in `error` and never
// thrown, so a single failing endpoint only affects its own section.
export function useApiData(fn) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [updatedAt, setUpdatedAt] = useState(null)
  const seq = useRef(0)

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
        setData(null)
      }
    } finally {
      if (id === seq.current) setLoading(false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    load()
  }, [load])

  return { data, loading, error, updatedAt, reload: load }
}

export default useApiData
