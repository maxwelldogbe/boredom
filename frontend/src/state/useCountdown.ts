import { useEffect, useState } from 'react'
import { useRoomState } from './context'

/** Client clock that re-renders every `intervalMs`. */
export function useNow(intervalMs = 100): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), intervalMs)
    return () => clearInterval(timer)
  }, [intervalMs])
  return now
}

/** Milliseconds left until a server deadline, corrected by the server clock offset. */
export function useRemainingMs(deadline: number | null): number | null {
  const now = useNow()
  const { clockOffset } = useRoomState()
  if (deadline === null) return null
  return Math.max(0, deadline - (now + clockOffset))
}
