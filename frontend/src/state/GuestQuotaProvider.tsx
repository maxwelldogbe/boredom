import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { onAuthChange } from '../lib/account'
import { errorCode } from '../lib/errors'
import { getProfile } from '../lib/profileStore'
import type { GuestQuota } from '../types/protocol'
import { useRoomActions } from './context'
import { GuestQuotaContext, type GuestQuotaState, type Quota } from './guestQuotaContext'

const isGuest = () => getProfile()?.type === 'guest'

function toLocal(data: GuestQuota): Quota {
  const lockedUntil = data.lockedUntil === null ? null : data.lockedUntil - data.serverNow + Date.now()
  return { remaining: data.remaining, limit: data.limit, lockedUntil }
}

/** Guests' free games (core/PROTOCOL.md 11): from guest:quota acks and pushes. */
export function GuestQuotaProvider({ children }: { children: ReactNode }) {
  const { socket } = useRoomActions()
  const [quota, setQuota] = useState<Quota | null>(null)
  const [now, setNow] = useState(() => Date.now())

  const apply = useCallback((data: GuestQuota) => {
    setNow(Date.now())
    setQuota(toLocal(data))
  }, [])

  const refresh = useCallback(() => {
    const profile = getProfile()
    if (profile?.type !== 'guest') return setQuota(null)
    socket
      .request('guest:quota', { profile: { id: profile.id } })
      .then((data) => isGuest() && apply(data))
      .catch(() => {}) // unknown: nothing is shown
  }, [socket, apply])

  useEffect(() => {
    const offPush = socket.onPush((msg) => {
      if (msg.type === 'guest:quota' && isGuest()) apply(msg.data)
    })
    const offAuth = onAuthChange(() => {
      if (!isGuest()) setQuota(null)
    })
    return () => {
      offPush()
      offAuth()
    }
  }, [socket, apply])

  // Re-render when the lock runs out, so the wall goes away without a reload.
  const lockedUntil = quota?.lockedUntil ?? null
  useEffect(() => {
    if (lockedUntil === null) return
    const timer = setTimeout(() => setNow(Date.now()), Math.max(0, lockedUntil - Date.now()) + 50)
    return () => clearTimeout(timer)
  }, [lockedUntil])

  const value = useMemo<GuestQuotaState>(
    () => ({
      quota,
      locked: lockedUntil !== null && now < lockedUntil,
      refresh,
      handleError: (err) => {
        if (errorCode(err) === 'GUEST_LIMIT') refresh()
      },
    }),
    [quota, lockedUntil, now, refresh],
  )
  return <GuestQuotaContext.Provider value={value}>{children}</GuestQuotaContext.Provider>
}
