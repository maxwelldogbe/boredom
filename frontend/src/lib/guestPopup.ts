/** Counters for the guest signup popup (src/config/guestPopup.ts), kept in localStorage with a
 *  memory fallback. */
import {
  BACKOFF_AFTER_DISMISSALS,
  BACKOFF_EVERY_GAMES,
  EVERY_GAMES,
  FIRST_AFTER_GAMES,
  MIN_MINUTES_BETWEEN,
  STORAGE_KEY,
} from '../config/guestPopup'
import { readItem, writeItem } from './storage'

export interface GuestPopupState {
  gamesSinceShown: number
  totalGames: number
  /** Epoch ms, or null if it has never been shown. */
  lastShownAt: number | null
  dismissalsInARow: number
}

const EMPTY: GuestPopupState = { gamesSinceShown: 0, totalGames: 0, lastShownAt: null, dismissalsInARow: 0 }

const count = (value: unknown) => (typeof value === 'number' && Number.isFinite(value) && value >= 0 ? Math.floor(value) : 0)

export function loadPopupState(): GuestPopupState {
  try {
    const raw = JSON.parse(readItem(STORAGE_KEY) ?? 'null') as Partial<GuestPopupState> | null
    if (!raw || typeof raw !== 'object') return { ...EMPTY }
    return {
      gamesSinceShown: count(raw.gamesSinceShown),
      totalGames: count(raw.totalGames),
      lastShownAt: typeof raw.lastShownAt === 'number' && Number.isFinite(raw.lastShownAt) ? raw.lastShownAt : null,
      dismissalsInARow: count(raw.dismissalsInARow),
    }
  } catch {
    return { ...EMPTY }
  }
}

function update(change: (state: GuestPopupState) => Partial<GuestPopupState>): GuestPopupState {
  const state = loadPopupState()
  const next = { ...state, ...change(state) }
  writeItem(STORAGE_KEY, JSON.stringify(next))
  return next
}

/** A finished game (completed or forfeit) that the guest played in. */
export const countFinishedGame = () =>
  update((s) => ({ gamesSinceShown: s.gamesSinceShown + 1, totalGames: s.totalGames + 1 }))

export function popupDue(state: GuestPopupState = loadPopupState(), now = Date.now()): boolean {
  if (state.lastShownAt === null) return state.totalGames >= FIRST_AFTER_GAMES
  const every = state.dismissalsInARow >= BACKOFF_AFTER_DISMISSALS ? BACKOFF_EVERY_GAMES : EVERY_GAMES
  return state.gamesSinceShown >= every && now - state.lastShownAt >= MIN_MINUTES_BETWEEN * 60_000
}

export const markPopupShown = (now = Date.now()) => update(() => ({ lastShownAt: now }))

/** "Maybe later" or ✕. */
export const dismissPopup = (now = Date.now()) =>
  update((s) => ({ dismissalsInARow: s.dismissalsInARow + 1, gamesSinceShown: 0, lastShownAt: now }))

/** "Create free account". */
export const convertPopup = (now = Date.now()) => update(() => ({ dismissalsInARow: 0, gamesSinceShown: 0, lastShownAt: now }))

/** The player created an account (from anywhere). */
export const resetPopupDismissals = () => update(() => ({ dismissalsInARow: 0 }))
