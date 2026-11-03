import { useCallback, useEffect, useState } from 'react'
import { getAuthToken } from '../lib/account'
import { getProfile } from '../lib/profileStore'
import { allRoomTokens } from '../lib/roomTokens'
import type { ResumeSeat } from '../types/protocol'
import { useRoomActions } from './context'

/** room:resume payload: the account's token, or a guest's stored room tokens (null: nothing). */
export function resumePayload(): { authToken: string } | { tokens: { code: string; roomToken: string }[] } | null {
  const token = getProfile()?.type === 'registered' ? getAuthToken() : null
  if (token) return { authToken: token }
  const tokens = allRoomTokens()
  return tokens.length ? { tokens } : null
}

/** The player's own seat the server still holds (PROTOCOL.md 4.11): asked on mount and after
 *  every reconnect. */
export function useResumeSeat(): { seat: ResumeSeat | null; refresh: () => void } {
  const { socket } = useRoomActions()
  const [seat, setSeat] = useState<ResumeSeat | null>(null)

  const refresh = useCallback(() => {
    const payload = resumePayload()
    const ask = payload ? socket.request('room:resume', payload) : Promise.resolve({ resume: null })
    ask
      .then((data) => setSeat(data.resume))
      .catch(() => {}) // nothing to offer this time; a reconnect asks again
  }, [socket])

  useEffect(() => {
    refresh()
    return socket.onOpen((isReconnect) => {
      if (isReconnect) refresh()
    })
  }, [socket, refresh])

  return { seat, refresh }
}
