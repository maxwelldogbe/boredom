/**
 * Friends, blocks, reports and the presence setting (core/PROTOCOL.md 8.7): the HTTP client
 * and the plain-language labels the screens share. Registered accounts only.
 */
import type {
  FriendRequestEntry,
  FriendStatus,
  PlayerCard,
  PresenceMode,
  ReportReason,
} from '../types/protocol'
import { AccountError, apiCall, getAuthToken, type MyStats } from './account'
import { C } from './constants'
import { errorCode, friendlyError } from './errors'

export interface Friend extends PlayerCard {
  status: FriendStatus
}

export interface FriendsOverview {
  friends: Friend[]
  incoming: FriendRequestEntry[]
  outgoing: FriendRequestEntry[]
  blocked: PlayerCard[]
}

export interface FriendProfile extends PlayerCard {
  /** ISO-8601 UTC */
  memberSince: string
  stats: MyStats
}

function token(): string {
  const value = getAuthToken()
  if (!value) throw new AccountError('UNAUTHORIZED', 'Please log in again.')
  return value
}

const enc = (tag: string) => encodeURIComponent(tag)

export const fetchFriends = () => apiCall<FriendsOverview>('GET', '/api/friends', undefined, token())

export const sendFriendRequest = (tag: string) =>
  apiCall<{ status: 'requested' | 'friends' }>('POST', '/api/friends/requests', { tag }, token())

export const acceptRequest = (id: number) =>
  apiCall<{ status: 'friends' }>('POST', `/api/friends/requests/${id}/accept`, undefined, token())

export const declineRequest = (id: number) =>
  apiCall('POST', `/api/friends/requests/${id}/decline`, undefined, token())

export const cancelRequest = (id: number) => apiCall('DELETE', `/api/friends/requests/${id}`, undefined, token())

export const removeFriend = (tag: string) => apiCall('DELETE', `/api/friends/${enc(tag)}`, undefined, token())

export const fetchFriendProfile = (tag: string) =>
  apiCall<FriendProfile>('GET', `/api/friends/${enc(tag)}/profile`, undefined, token())

export const blockPlayer = (tag: string) => apiCall('POST', '/api/blocks', { tag }, token())

export const unblockPlayer = (tag: string) => apiCall('DELETE', `/api/blocks/${enc(tag)}`, undefined, token())

export const reportPlayer = (tag: string, reason: ReportReason, note: string) =>
  apiCall('POST', '/api/reports', { tag, reason, ...(note.trim() ? { note: note.trim() } : {}) }, token())

export const fetchSettings = () => apiCall<{ presence: PresenceMode }>('GET', '/api/me/settings', undefined, token())

export const savePresence = (presence: PresenceMode) =>
  apiCall<{ presence: PresenceMode }>('PATCH', '/api/me/settings', { presence }, token())

// ----- tags --------------------------------------------------------------------------

const TAG_CHARS = new RegExp(`[^${C.TAG_ALPHABET}]`, 'g')

/** What the add-friend field keeps from typing or pasting "#k7m2qx": "K7M2QX". */
export function cleanTagInput(raw: string): string {
  return raw.toUpperCase().replace(TAG_CHARS, '').slice(0, C.TAG_LENGTH)
}

// ----- labels ------------------------------------------------------------------------

export const STATUS_LABELS: Record<FriendStatus, { icon: string; label: string }> = {
  online: { icon: '●', label: 'Online' },
  in_lobby: { icon: '🚪', label: 'In a lobby' },
  in_game: { icon: '🎮', label: 'In a game' },
  busy: { icon: '⛔', label: 'Busy' },
  offline: { icon: '○', label: 'Offline' },
}

export const STATUS_ORDER: FriendStatus[] = ['online', 'in_lobby', 'in_game', 'busy', 'offline']

export const PRESENCE_OPTIONS: { value: PresenceMode; label: string; hint: string }[] = [
  { value: 'online', label: 'Online', hint: 'Friends see when you are around and can invite you.' },
  { value: 'busy', label: 'Busy', hint: 'Friends see you are busy and cannot invite you.' },
  { value: 'offline', label: 'Appear offline', hint: 'You look offline to everyone. No invites.' },
]

export const REASON_LABELS: Record<ReportReason, string> = {
  harassment: 'Harassment or bullying',
  inappropriate_name_or_avatar: 'Inappropriate name or avatar',
  cheating: 'Cheating',
  spam: 'Spam',
  other: 'Something else',
}

export const REPORT_REASONS = C.REPORT_REASONS as ReportReason[]

/** Messages for the add-friend field, by error code. */
export function friendRequestError(err: unknown): string {
  if (!(err instanceof AccountError)) return 'Something went wrong. Please try again.'
  switch (err.code) {
    case 'INVALID_INPUT':
      return `A tag is ${C.TAG_LENGTH} letters and numbers, like #K7M2QX.`
    case 'NOT_FOUND':
      return "We couldn't find a player with that tag. Check it and try again."
    case 'SELF':
      return "That's your own tag."
    case 'ALREADY_FRIENDS':
      return "You're already friends."
    case 'ALREADY_REQUESTED':
      return 'You already sent them a request.'
    case 'LIMIT_REACHED':
      return err.message || 'You have reached the limit for friends or requests.'
    case 'RATE_LIMITED':
      return 'You sent a lot of requests. Try again in a while.'
    case 'NETWORK':
      return err.message
    default:
      return 'Something went wrong. Please try again.'
  }
}

/** A short message for any other failed social request. */
export function socialError(err: unknown): string {
  if (err instanceof AccountError) {
    if (err.code === 'RATE_LIMITED') return 'Too many tries. Please wait a while.'
    return Object.values(err.fields)[0] ?? err.message
  }
  return 'Something went wrong. Please try again.'
}

/** invite:send failures. Never says why a friend can't be invited. */
export function inviteSendError(err: unknown): string {
  switch (errorCode(err)) {
    case 'TARGET_UNAVAILABLE':
      return "They can't be invited right now."
    case 'RATE_LIMITED':
      return (err as Error).message || 'Too many invites. Wait a moment.'
    case 'ROOM_FULL':
      return 'Your room is full.'
    case 'NOT_FRIENDS':
      return 'You can only invite friends.'
    case 'INVALID_ACTION':
      return 'You can only invite friends from the lobby.'
    default:
      return friendlyError(err)
  }
}

/** invite:accept failures. */
export function inviteAcceptError(err: unknown): string {
  switch (errorCode(err)) {
    case 'INVITE_EXPIRED':
      return 'That invite has expired.'
    case 'INVITE_INVALID':
      return 'That invite is no longer available.'
    case 'ROOM_FULL':
      return 'That room is full.'
    default:
      return friendlyError(err)
  }
}
