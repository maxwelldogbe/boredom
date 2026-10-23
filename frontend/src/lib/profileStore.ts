/** Guest profile stored in the browser under `partypack.profile` (plan 5.1). */
import type { WireProfile } from '../types/protocol'
import { C } from './constants'
import { readItem, removeItem, writeItem } from './storage'

export const PROFILE_KEY = 'partypack.profile'

export interface Stats {
  gamesPlayed: number
  wins: number
  byGame: Record<string, { played: number; wins: number }>
}

export interface Profile {
  id: string
  nickname: string
  color: string
  type: 'guest' | 'registered'
  createdAt: number
  stats: Stats
}

export type ProfileFields = Pick<Profile, 'nickname' | 'color'>

const NICKNAME_RE = new RegExp(C.NICKNAME_ALLOWED_PATTERN)

/** Returns an error message, or null when the nickname is valid. */
export function nicknameError(raw: string): string | null {
  const nickname = raw.trim()
  if (nickname.length < C.NICKNAME_MIN) return 'Enter a nickname.'
  if (nickname.length > C.NICKNAME_MAX) return `Use at most ${C.NICKNAME_MAX} characters.`
  if (!NICKNAME_RE.test(nickname)) return "Use letters, numbers, spaces and _ . ' ! ? & - only."
  return null
}

function emptyStats(): Stats {
  return { gamesPlayed: 0, wins: 0, byGame: {} }
}

/** A random id. crypto.randomUUID needs HTTPS, so phones on a LAN dev server fall back. */
export function newId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    try {
      return crypto.randomUUID()
    } catch {
      // insecure context
    }
  }
  const bytes = new Uint8Array(16)
  crypto.getRandomValues(bytes)
  bytes[6] = (bytes[6] & 0x0f) | 0x40
  bytes[8] = (bytes[8] & 0x3f) | 0x80
  const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('')
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`
}

/** Validate unknown data as a Profile; returns null if anything is wrong.
 * Profiles saved before avatars existed still load: their old `emoji` field is dropped. */
export function parseProfile(data: unknown): Profile | null {
  if (!data || typeof data !== 'object') return null
  const p = data as Record<string, unknown>
  if (typeof p.id !== 'string' || !p.id || p.id.length > 64) return null
  if (typeof p.nickname !== 'string' || nicknameError(p.nickname)) return null
  if (typeof p.color !== 'string' || !C.PLAYER_COLORS.includes(p.color)) return null
  const createdAt = typeof p.createdAt === 'number' ? p.createdAt : Date.now()
  const s = p.stats as Partial<Stats> | undefined
  const stats: Stats =
    s && typeof s.gamesPlayed === 'number' && typeof s.wins === 'number' && s.byGame
      ? { gamesPlayed: s.gamesPlayed, wins: s.wins, byGame: { ...s.byGame } }
      : emptyStats()
  return {
    id: p.id,
    nickname: p.nickname.trim(),
    color: p.color,
    type: 'guest',
    createdAt,
    stats,
  }
}

export function getProfile(): Profile | null {
  try {
    const raw = readItem(PROFILE_KEY)
    return raw ? parseProfile(JSON.parse(raw)) : null
  } catch {
    return null
  }
}

export function saveProfile(profile: Profile): void {
  writeItem(PROFILE_KEY, JSON.stringify(profile))
}

export function resetProfile(): void {
  removeItem(PROFILE_KEY)
}

/** Build a brand-new guest profile from the setup form. */
export function createProfile(fields: ProfileFields): Profile {
  return {
    id: newId(),
    nickname: fields.nickname.trim(),
    color: fields.color,
    type: 'guest',
    createdAt: Date.now(),
    stats: emptyStats(),
  }
}

/** Trigger a download of the profile as JSON. */
export function exportProfile(profile: Profile): void {
  const blob = new Blob([JSON.stringify(profile, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `boredom-profile-${profile.nickname}.json`
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

export type ImportResult = { ok: true; profile: Profile } | { ok: false; error: string }

/** Validate an exported file's text; does not save. */
export function importProfile(text: string): ImportResult {
  try {
    const profile = parseProfile(JSON.parse(text))
    if (profile) return { ok: true, profile }
  } catch {
    // fall through
  }
  return { ok: false, error: "That file isn't a valid Boredom profile." }
}

/** The fields the server accepts (stats never leave the browser). */
export function toWireProfile(profile: Profile): WireProfile {
  return {
    id: profile.id,
    nickname: profile.nickname,
    color: profile.color,
    type: profile.type,
  }
}
