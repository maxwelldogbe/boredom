import { useCallback, useEffect, useState } from 'react'
import { AdminApiError, adminGet } from './api'
import { useAdminSession } from './session'

type Params = Record<string, string | number | null | undefined>

interface Result<T> {
  key: string
  data: T | null
  error: AdminApiError | null
}

/**
 * Fetch a dashboard endpoint. While refetching (a filter changed) the previous data stays on
 * screen, flagged `refreshing`, so charts hold their frame instead of flashing.
 */
export function useAdminData<T>(path: string, params: Params = {}) {
  const { onUnauthorized } = useAdminSession()
  const [tick, setTick] = useState(0)
  const [result, setResult] = useState<Result<T>>({ key: '', data: null, error: null })
  const key = `${path}?${JSON.stringify(params)}#${tick}`

  useEffect(() => {
    let live = true
    adminGet<T>(path, params)
      .then((data) => {
        if (live) setResult({ key, data, error: null })
      })
      .catch((err: unknown) => {
        if (!live) return
        const error = err instanceof AdminApiError ? err : new AdminApiError(0, 'SERVER', 'Something went wrong.')
        if (error.status === 401 || error.status === 403) onUnauthorized()
        setResult((prev) => ({ key, data: prev.data, error }))
      })
    return () => {
      live = false
    }
    // `key` captures path, params and reloads.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key])

  const reload = useCallback(() => setTick((t) => t + 1), [])
  const loading = result.key !== key
  return {
    data: result.data,
    error: loading ? null : result.error,
    loading,
    refreshing: loading && result.data !== null,
    reload,
  }
}
