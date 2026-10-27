import { createContext, useContext } from 'react'

/** A guest's free games, with `lockedUntil` on this device's clock (server offset corrected). */
export interface Quota {
  remaining: number
  limit: number
  lockedUntil: number | null
}

export interface GuestQuotaState {
  /** null until known, and always for registered players. */
  quota: Quota | null
  /** True for a locked guest until the countdown ends. */
  locked: boolean
  /** Ask the server (guests only). */
  refresh(): void
  /** After any failed request: a GUEST_LIMIT error refreshes the quota (showing the wall). */
  handleError(err: unknown): void
}

const NONE: GuestQuotaState = { quota: null, locked: false, refresh: () => {}, handleError: () => {} }

export const GuestQuotaContext = createContext<GuestQuotaState>(NONE)

export const useGuestQuota = () => useContext(GuestQuotaContext)
