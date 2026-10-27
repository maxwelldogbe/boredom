import { useCallback, useEffect, useState } from 'react'
import { AccountError } from '../../lib/account'

export type Load<T> = { status: 'loading' } | { status: 'ready'; data: T } | { status: 'error'; message: string }

/** Fetch once on mount and on retry(). An expired login calls `onExpired` instead. */
export function useLoad<T>(fetcher: () => Promise<T>, onExpired: () => void): [Load<T>, () => void] {
  const [state, setState] = useState<Load<T>>({ status: 'loading' })
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    let live = true
    Promise.resolve()
      .then(fetcher) // a synchronous throw becomes a rejection too
      .then((data) => live && setState({ status: 'ready', data }))
      .catch((err: unknown) => {
        if (!live) return
        if (err instanceof AccountError && err.code === 'UNAUTHORIZED') return onExpired()
        setState({ status: 'error', message: err instanceof AccountError ? err.message : 'Something went wrong.' })
      })
    return () => {
      live = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- once per attempt
  }, [attempt])
  const retry = useCallback(() => {
    setState({ status: 'loading' })
    setAttempt((n) => n + 1)
  }, [])
  return [state, retry]
}

