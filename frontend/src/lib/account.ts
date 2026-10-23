/**
 * Optional permanent accounts (core/PROTOCOL.md section 8): the HTTP API client, the stored
 * access token, and mapping the saved account onto the local profile.
 */
import type { Avatar } from '../types/protocol'
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
}

export type AccountStats = Stats

export type AccountErrorCode =
  | 'INVALID_INPUT'
  | 'INVALID_CREDENTIALS'
  | 'UNAUTHORIZED'
  | 'USERNAME_TAKEN'
  | 'RATE_LIMITED'
  | 'METHOD_NOT_ALLOWED'
  | 'NETWORK'
  | 'SERVER'

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

export function getAuthToken(): string | null {
  return readItem(AUTH_KEY)
}

export function setAuthToken(token: string): void {
  writeItem(AUTH_KEY, token)
}

export function clearAuthToken(): void {
  removeItem(AUTH_KEY)
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

async function call<T>(method: Method, path: string, body?: unknown, token?: string | null): Promise<T> {
  const headers: Record<string, string> = { Accept: 'application/json' }
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  if (token) headers.Authorization = `Bearer ${token}`
  let response: Response
  try {
    response = await fetch(apiUrl(`/api/auth/${path}`), {
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
  const data = await call<{ token: string; profile: AccountProfile }>('POST', 'register', {
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
  return call<Session>('POST', 'login', { username, password })
}

export function fetchMe(token: string): Promise<{ profile: AccountProfile; stats: AccountStats }> {
  return call('GET', 'me', undefined, token)
}

export async function updateAccountProfile(
  token: string,
  fields: { nickname?: string; color?: string },
): Promise<AccountProfile> {
  return (await call<{ profile: AccountProfile }>('PATCH', 'profile', fields, token)).profile
}

export async function deleteAccount(token: string, password: string): Promise<void> {
  await call('DELETE', 'account', { password }, token)
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

