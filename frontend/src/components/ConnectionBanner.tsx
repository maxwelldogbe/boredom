import { useEffect, useRef, useState, type ReactNode } from 'react'
import { useRoomActions, useRoomState } from '../state/context'

export const BANNER_DELAY_MS = 1500

/** "Connection lost. Reconnecting..." after BANNER_DELAY_MS offline; "Back online" when it
 *  returns. Never navigates or clears the room: the socket reconnects and the seat is rejoined. */
export function ConnectionBanner() {
  const { connection } = useRoomState()
  const { toast } = useRoomActions()
  const [shown, setShown] = useState(false)
  const wasShown = useRef(false)

  useEffect(() => {
    if (connection === 'connected') {
      if (wasShown.current) toast('Back online')
      wasShown.current = false
      const timer = setTimeout(() => setShown(false), 0)
      return () => clearTimeout(timer)
    }
    const timer = setTimeout(() => {
      wasShown.current = true
      setShown(true)
    }, BANNER_DELAY_MS)
    return () => clearTimeout(timer)
  }, [connection, toast])

  return (
    <div aria-live="polite">
      {shown && connection !== 'connected' && <p className="connection-banner">Connection lost. Reconnecting...</p>}
    </div>
  )
}

/** Controls inside are disabled while the connection is down (nothing the server must answer). */
export function OnlineOnly({ children }: { children: ReactNode }) {
  const { connection } = useRoomState()
  return (
    <fieldset className="online-only" disabled={connection !== 'connected'}>
      {children}
    </fieldset>
  )
}
