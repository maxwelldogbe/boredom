/**
 * Optional permanent accounts (core/PROTOCOL.md section 8): the HTTP API client, the stored
 * access token, and mapping the saved account onto the local profile.
 */
import type { Avatar, GameId } from '../types/protocol'
import { C } from './constants'
import { apiUrl } from './endpoints'
import { getProfile, newId, saveProfile, toGuest, type Profile, type Stats } from './profileStore'
import { readItem, removeItem, writeItem } from './storage'

export const AUTH_KEY = 'partypack.authToken'

export interface AccountProfile {
  username: string
  nickname: string
  color: string
  avatar: Avatar
  type: 'registered'
  createdAt: number
  /** Epoch ms of the next allowed avatar change; null (or missing on old servers) means now. */
  avatarLockedUntil?: number | null
}

export type AccountStats = Stats

export type AccountErrorCode =
  | 'INVALID_INPUT'
  | 'INVALID_CREDENTIALS'
  | 'UNAUTHORIZED'
  | 'USERNAME_TAKEN'
  | 'AVATAR_LOCKED'
  | 'RATE_LIMITED'
  | 'METHOD_NOT_ALLOWED'
  | 'NETWORK'
  | 'SERVER'
  | 'NOT_FOUND'
  | 'FORBIDDEN'
  | 'SELF'
  | 'ALREADY_FRIENDS'
  | 'ALREADY_REQUESTED'
  | 'LIMIT_REACHED'

/** A failed account request. `fields` maps a form field to a message to show next to it. */
export class AccountError extends Error {
  readonly code: AccountErrorCode
  readonly fields: Record<string, string>
  constructor(code: AccountErrorCode, message: string, fields: Record<string, string> = {}) {
    super(message)
    this.code = code
    this.fields = fields
  }
}

// ----- token -------------------------------------------------------------------------

const authListeners = new Set<() => void>()

/** Called whenever this device logs in or out (the socket re-sends auth:hello). */
export function onAuthChange(fn: () => void): () => void {
  authListeners.add(fn)
  return () => authListeners.delete(fn)
}

export function getAuthToken(): string | null {
  return readItem(AUTH_KEY)
}

export function setAuthToken(token: string): void {
  const changed = readItem(AUTH_KEY) !== token
  writeItem(AUTH_KEY, token)
  if (changed) authListeners.forEach((fn) => fn())
}

export function clearAuthToken(): void {
  const changed = readItem(AUTH_KEY) !== null
  removeItem(AUTH_KEY)
  if (changed) authListeners.forEach((fn) => fn())
}

// ----- validation shared with the forms ----------------------------------------------

const USERNAME_RE = new RegExp(C.USERNAME_PATTERN)

export function usernameError(raw: string): string | null {
  if (!raw) return 'Choose a username.'
  if (!USERNAME_RE.test(raw)) return 'Use 3 to 20 letters, numbers or underscores.'
  return null
}

export function passwordError(raw: string): string | null {
  if (raw.length < C.PASSWORD_MIN_LENGTH) return `Use at least ${C.PASSWORD_MIN_LENGTH} characters.`
  return null
}

// ----- HTTP --------------------------------------------------------------------------

type Method = 'GET' | 'POST' | 'PATCH' | 'DELETE'

const FRIENDLY: Partial<Record<AccountErrorCode, string>> = {
  INVALID_CREDENTIALS: 'Wrong username or password.',
  UNAUTHORIZED: 'Please log in again.',
  USERNAME_TAKEN: 'That username is taken.',
  RATE_LIMITED: 'Too many attempts. Wait a minute and try again.',
}

/** `path` is under /api/auth/, or a full path starting with "/" (e.g. /api/me/stats). */
export async function apiCall<T>(method: Method, path: string, body?: unknown, token?: string | null): Promise<T> {
  const headers: Record<string, string> = { Accept: 'application/json' }
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  if (token) headers.Authorization = `Bearer ${token}`
  let response: Response
  try {
    response = await fetch(apiUrl(path.startsWith('/') ? path : `/api/auth/${path}`), {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    })
  } catch {
    throw new AccountError('NETWORK', "Can't reach the server. Check your connection and try again.")
  }
  const data: unknown = await response.json().catch(() => null)
  if (response.ok) return data as T
  const error = (data as { error?: { code?: string; message?: string; fields?: Record<string, string> } } | null)
    ?.error
  const code = (error?.code ?? 'SERVER') as AccountErrorCode
  const message = FRIENDLY[code] ?? error?.message ?? 'Something went wrong. Please try again.'
  throw new AccountError(code, message, error?.fields ?? {})
}

export interface Session {
  token: string
  profile: AccountProfile
  stats: AccountStats
}

const EMPTY_STATS: AccountStats = { gamesPlayed: 0, wins: 0, byGame: {} }

/** Create an account from the guest profile: its avatar is claimed and its stats imported. */
export async function register(username: string, password: string, guest: Profile): Promise<Session> {
  const data = await apiCall<{ token: string; profile: AccountProfile }>('POST', 'register', {
    username,
    password,
    profile: {
      nickname: guest.nickname,
      color: guest.color,
      ...(guest.avatar ? { avatar: guest.avatar } : {}),
      stats: guest.stats,
    },
  })
  // A new account's stats are the imported guest stats, if the server kept them.
  const me = await fetchMe(data.token).catch(() => ({ profile: data.profile, stats: EMPTY_STATS }))
  return { token: data.token, profile: me.profile, stats: me.stats }
}

export function login(username: string, password: string): Promise<Session> {
  return apiCall<Session>('POST', 'login', { username, password })
}

export interface MeData {
  profile: AccountProfile
  stats: AccountStats
  /** Public tag, shown as "#" + tag. Missing from servers before the profile page. */
  tag?: string
  /** Registration time, ISO-8601 UTC. Missing from servers before the profile page. */
  createdAt?: string
}

export function fetchMe(token: string): Promise<MeData> {
  return apiCall('GET', 'me', undefined, token)
}

export interface GameTotals {
  played: number
  wins: number
  losses: number
  /** 0..1; null until `minGamesForRate` games. Computed by the server. */
  winRate: number | null
}

export interface MyStats {
  totals: GameTotals
  favoriteGame: GameId | null
  perGame: (GameTotals & { gameId: GameId })[]
  minGamesForRate: number
}

export interface RecentPlayer {
  tag: string
  nickname: string
  avatar: Avatar
  color: string
  lastPlayedAt: string
  gamesTogether: number
  lastGameId: GameId
  /** requested: you asked them; incoming: they asked you. Missing from older servers. */
  relationship?: 'none' | 'friends' | 'requested' | 'incoming'
}

export function fetchMyStats(token: string): Promise<MyStats> {
  return apiCall('GET', '/api/me/stats', undefined, token)
}

export async function fetchRecentPlayers(token: string): Promise<RecentPlayer[]> {
  return (await apiCall<{ players: RecentPlayer[] }>('GET', '/api/me/recent-players', undefined, token)).players
}

export async function updateAccountProfile(
  token: string,
  fields: { nickname?: string; color?: string; avatar?: Avatar },
): Promise<AccountProfile> {
  return (await apiCall<{ profile: AccountProfile }>('PATCH', 'profile', fields, token)).profile
}

export async function deleteAccount(token: string, password: string): Promise<void> {
  await apiCall('DELETE', 'account', { password }, token)
}

// ----- local profile -----------------------------------------------------------------

/** Save the account onto this device's profile (creating one if needed) and keep the token. */
export function adoptSession(session: { token?: string; profile: AccountProfile; stats: AccountStats }): Profile {
  if (session.token) setAuthToken(session.token)
  const current = getProfile()
  const profile: Profile = {
    id: current?.id ?? newId(),
    createdAt: current?.createdAt ?? session.profile.createdAt,
    nickname: session.profile.nickname,
    color: session.profile.color,
    type: 'registered',
    username: session.profile.username,
    avatar: session.profile.avatar,
    stats: session.stats,
  }
  saveProfile(profile)
  return profile
}

/** Forget the login on this device; the profile becomes a guest again. */
export function forgetAccount(): Profile | null {
  clearAuthToken()
  const current = getProfile()
  if (!current) return null
  const guest = toGuest(current)
  saveProfile(guest)
  return guest
}

