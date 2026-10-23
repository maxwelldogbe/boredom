/**
 * Client for the staff JSON API (/api/admin/, see core/analytics/api.py).
 * Authentication is the Django admin session cookie, so the dashboard must be served from the
 * same origin as the API (the Vite proxy does this in development).
 */
import { apiUrl } from '../lib/endpoints'

export interface RangeOption {
  key: string
  label: string
}

export interface GameRef {
  id: string
  name: string
}

/** A registered account or a guest (guests are identified only by a pseudonymous key). */
export interface ActorRef {
  kind: 'registered' | 'guest'
  userId: number | null
  guestKey: string | null
  shortKey?: string
  name: string
}

export interface AdminSession {
  staff: boolean
  username: string | null
  superuser: boolean
  csrfToken: string
  loginUrl: string
  logoutUrl: string
  adminUrl: string
  exports: { users: string; sessions: string }
  timeZone: string
  minGamesForRates: number
}

export interface DayCount {
  date: string
  count: number
}

export interface LiveRoom {
  code: string
  status: string
  game: string
  players: number
  online: number
}

export interface OverviewData {
  range: RangeOption
  ranges: RangeOption[]
  sessions: {
    completed: number
    abandoned: number
    today: number
    avgPlayers: number | null
    avgDuration: number | null
    abandonRate: number | null
  }
  mostPlayed: (GameRef & { plays: number }) | null
  users: { total: number; new: number }
  guestsSeen: number
  active: { daily: number; weekly: number; monthly: number }
  perDay: DayCount[]
  live: LiveRoom[]
  cachedSeconds: number
}

export interface GameRow extends GameRef {
  plays: number
  abandoned: number
  uniquePlayers: number
  avgPlayers: number | null
  avgDuration: number | null
  completionRate: number | null
}

export interface GamesData {
  range: RangeOption
  ranges: RangeOption[]
  games: GameRow[]
}

export interface GameDetailData {
  range: RangeOption
  ranges: RangeOption[]
  game: GameRef
  totals: Omit<GameRow, keyof GameRef>
  perDay: DayCount[]
  recent: Array<{
    id: number
    status: 'completed' | 'abandoned'
    startedAt: string
    durationSeconds: number
    playerCount: number
    roomCode: string
  }>
}

export interface Paged {
  page: number
  numPages: number
  count: number
  pageSize: number
}

export interface UserRow extends ActorRef {
  username: string | null
  firstSeen: string | null
  lastSeen: string | null
  games: number
  wins: number
  losses: number
  winRate: number | null
  favorite: GameRef | null
}

export interface UsersData extends Paged {
  query: { q: string; type: string; sort: string; dir: 'asc' | 'desc' }
  sorts: string[]
  minGamesForRates: number
  results: UserRow[]
}

export interface ActivityItem {
  id: number
  kind: string
  label: string
  occurredAt: string
  roomCode: string
  game: GameRef | null
}

export interface UserDetailData {
  actor: ActorRef & { username: string | null; joined: string | null; isActive: boolean | null }
  permissions: { change: boolean; delete: boolean }
  minGamesForRates: number
  totals: {
    games: number
    wins: number
    losses: number
    abandoned: number
    winRate: number | null
    firstGame: string | null
    lastGame: string | null
  }
  perGame: Array<
    GameRef & {
      played: number
      wins: number
      losses: number
      winRate: number | null
      avgPlacement: number | null
    }
  >
  mostPlayed: GameRef | null
  mostWon: GameRef | null
  mostLost: GameRef | null
  recent: Array<{
    startedAt: string
    game: GameRef | null
    status: 'completed' | 'abandoned'
    placement: number | null
    leftEarly: boolean
    opponents: string[]
  }>
  coPlayers: Array<ActorRef & { shared: number; ahead: number; behind: number }>
  events: ActivityItem[]
}

export interface LeaderRow extends ActorRef {
  games: number
  wins: number
  winRate: number | null
}

export interface LeaderboardsData {
  game: GameRef | null
  games: GameRef[]
  minGamesForRates: number
  mostWins: LeaderRow[]
  bestRate: LeaderRow[]
  mostGames: LeaderRow[]
}

export interface ActivityData extends Paged {
  query: { kind: string; game: string; date: string | null }
  kinds: Array<{ value: string; label: string }>
  games: GameRef[]
  results: Array<ActivityItem & { who: ActorRef | null }>
}

/** A failed admin request. `loginUrl` is set when the session is missing or not staff. */
export class AdminApiError extends Error {
  readonly status: number
  readonly code: string
  readonly loginUrl: string | null
  constructor(status: number, code: string, message: string, loginUrl: string | null = null) {
    super(message)
    this.status = status
    this.code = code
    this.loginUrl = loginUrl
  }
}

async function send<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response
  try {
    response = await fetch(apiUrl(`/api/admin/${path}`), {
      credentials: 'same-origin',
      ...init,
      headers: { Accept: 'application/json', ...(init.headers ?? {}) },
    })
  } catch {
    throw new AdminApiError(0, 'NETWORK', "Can't reach the server.")
  }
  const data: unknown = await response.json().catch(() => null)
  if (response.ok) return data as T
  const error = (data as { error?: { code?: string; message?: string; loginUrl?: string } } | null)?.error
  throw new AdminApiError(
    response.status,
    error?.code ?? (response.status === 403 ? 'FORBIDDEN' : 'SERVER'),
    error?.message ?? 'Something went wrong.',
    error?.loginUrl ?? null,
  )
}

export function getSession(): Promise<AdminSession> {
  return send('session')
}

/** GET a dashboard endpoint, with query parameters (empty values are left out). */
export function adminGet<T>(path: string, params: Record<string, string | number | null | undefined> = {}) {
  const query = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== null && value !== undefined && value !== '') query.set(key, String(value))
  }
  const qs = query.toString()
  return send<T>(qs ? `${path}?${qs}` : path)
}

export function userAction(userId: number, action: 'disable' | 'enable' | 'delete', csrfToken: string) {
  return send<{ ok: true; isActive?: boolean; deleted?: boolean }>(`users/u/${userId}/${action}`, {
    method: 'POST',
    headers: { 'X-CSRFToken': csrfToken },
  })
}

/** Log out of the admin session (Django's admin logout needs a POST with the CSRF token). */
export async function logout(session: AdminSession): Promise<void> {
  const body = new URLSearchParams({ csrfmiddlewaretoken: session.csrfToken })
  await fetch(session.logoutUrl, { method: 'POST', credentials: 'same-origin', body }).catch(() => undefined)
}
