/**
 * Wire types for the Boredom WebSocket protocol, mirroring core/PROTOCOL.md
 * (verified against the live backend). Game views are in ./views.ts.
 */
import type { GameViewPush } from './views'

export type GameId = 'rps' | 'guess_race' | 'hangman' | 'dots_and_boxes' | 'liars_dice' | 'name_it'

export type ErrorCode =
  | 'ROOM_NOT_FOUND'
  | 'ROOM_FULL'
  | 'NAME_TAKEN'
  | 'NOT_HOST'
  | 'NOT_YOUR_TURN'
  | 'INVALID_ACTION'
  | 'GAME_IN_PROGRESS'
  | 'RATE_LIMITED'
  | 'NOT_IN_ROOM'
  | 'UNKNOWN_EVENT'
  | 'BAD_MESSAGE'
  | 'UNAUTHORIZED'
  | 'NOT_FRIENDS'
  | 'TARGET_UNAVAILABLE'
  | 'INVITE_EXPIRED'
  | 'INVITE_INVALID'
  | 'SELF'
  | 'ALREADY_FRIENDS'
  | 'ALREADY_REQUESTED'
  | 'LIMIT_REACHED'
  | 'INVALID_INPUT'
  | 'GUEST_LIMIT'

export interface ProtocolError {
  code: ErrorCode
  message: string
  /** GUEST_LIMIT: {lockedUntil} on room:create / room:join, {nicknames} on game:start. */
  data?: Record<string, unknown>
}

/** DiceBear avatar, assigned by the server per seat. The client builds the image URL. */
export interface Avatar {
  style: string
  seed: string
}

/** Profile as sent to the server (`room:create` / `room:join`). Guests get a server-picked avatar. */
export interface WireProfile {
  id: string
  nickname: string
  color: string
}

export type PlayerType = 'guest' | 'registered'

export interface Player {
  id: string
  /** "registered" seats belong to an account (show a badge); no account id is ever sent. */
  type: PlayerType
  nickname: string
  color: string
  avatar: Avatar
  online: boolean
  inGame: boolean
  joinedAt: number
  /** Lobby ready check; always false for the host. Missing from servers before the ready check. */
  ready?: boolean
  /** A guest out of free games (sits games out). Missing from older servers. */
  locked?: boolean
}

export type RoomStatus = 'lobby' | 'playing' | 'between_rounds' | 'finished'

export interface RoomPublic {
  code: string
  hostId: string
  status: RoomStatus
  players: Player[]
  selectedGame: GameId | null
  settings: Record<string, unknown>
  scoreboard: Record<string, number>
  wins: Record<string, number>
  /** Online non-host players who are ready, out of all of them. Null while no game is selected;
   *  missing from servers before the ready check. */
  readyCheck?: ReadyCheck | null
}

export interface ReadyCheck {
  count: number
  total: number
}

export interface GameResult {
  playerId: string
  placement: number
  /** Raw in-game score, for display only (meaning per game). */
  score: number
  /** Session points this game added to the scoreboard (placement-based, up to 2 decimals). */
  points: number
}

/** Ack data of room:create and room:join. */
export interface SeatData {
  playerId: string
  roomToken: string
  room: RoomPublic
  /** Present when the sent authToken was invalid or expired: the seat is a guest seat. */
  authStatus?: 'invalid'
}

export interface PeekData {
  exists: boolean
  hostNickname: string | null
  playerCount: number
  status: RoomStatus | null
}

type Empty = Record<string, never>

// ----- friends, presence and invites (PROTOCOL.md section 9) -----

export type FriendStatus = 'online' | 'in_lobby' | 'in_game' | 'busy' | 'offline'
export type PresenceMode = 'online' | 'busy' | 'offline'
export type ReportReason = 'harassment' | 'inappropriate_name_or_avatar' | 'cheating' | 'spam' | 'other'

/** A player named by their public tag (shown as "#" + tag). */
export interface PlayerCard {
  tag: string
  nickname: string
  avatar: Avatar
  color: string
}

export interface FriendRequestEntry extends PlayerCard {
  requestId: number
  /** ISO-8601 UTC */
  createdAt: string
}

/** invite:received: never contains the room code. */
export interface InvitePush {
  inviteId: string
  fromTag: string
  fromNickname: string
  fromAvatar: Avatar
  gameId: GameId | null
  /** Server epoch ms; count down `expiresAt - serverNow` from arrival. */
  expiresAt: number
  serverNow: number
}

/** guest:quota ack and push. Times are server epoch ms. */
export interface GuestQuota {
  remaining: number
  limit: number
  lockedUntil: number | null
  serverNow: number
}

/** Every request type with its payload and its ack `data`. */
export interface RequestMap {
  'room:create': { payload: { profile: WireProfile; authToken?: string }; data: SeatData }
  'room:join': {
    payload: { code: string; profile: WireProfile; roomToken?: string; authToken?: string }
    data: SeatData
  }
  'room:peek': { payload: { code: string }; data: PeekData }
  'room:leave': { payload: Empty; data: Empty }
  'game:quit': { payload: Empty; data: Empty }
  'room:selectGame': {
    payload: { gameId: GameId; settings: Record<string, unknown> }
    data: Empty
  }
  'game:start': { payload: Empty; data: Empty }
  'game:action': { payload: { type: string } & Record<string, unknown>; data: Empty }
  'game:playAgain': { payload: Empty; data: Empty }
  'room:ready': { payload: { ready: boolean }; data: Empty }
  'room:react': { payload: { emoji: string }; data: Empty }
  'guest:quota': { payload: { profile: { id: string } }; data: GuestQuota }
  'auth:hello': { payload: { authToken?: string }; data: { presence: PresenceMode } }
  'invite:send': { payload: { tag: string }; data: Empty }
  'invite:accept': { payload: { inviteId: string }; data: { code: string } }
  'invite:decline': { payload: { inviteId: string }; data: Empty }
  'friends:requestByPlayer': { payload: { playerId: string }; data: { status: 'requested' | 'friends' } }
  'player:block': { payload: { playerId: string }; data: Empty }
  'player:report': { payload: { playerId: string; reason: ReportReason; note?: string }; data: Empty }
}

export type RequestType = keyof RequestMap
export type RequestPayload<K extends RequestType> = RequestMap[K]['payload']
export type AckData<K extends RequestType> = RequestMap[K]['data']

export interface RequestMessage<K extends RequestType = RequestType> {
  id: number
  type: K
  payload: RequestPayload<K>
}

export type AckMessage =
  | { type: 'ack'; id: number; ok: true; data: unknown }
  | { type: 'ack'; id: number; ok: false; error: ProtocolError }

export interface GameEventPush {
  kind: string
  data: Record<string, unknown>
}

export interface RoomEventPush {
  kind: string
  playerId: string
  nickname: string
  data?: Record<string, unknown>
}

/** An emoji reaction, pushed to everyone in the room (the sender too). Never replayed. */
export interface ReactionPush {
  id: string
  playerId: string
  nickname: string
  emoji: string
}

export interface GameOverData {
  results: GameResult[]
}

export type PushMessage =
  | { type: 'room:state'; data: RoomPublic }
  | { type: 'game:view'; data: GameViewPush }
  | { type: 'game:event'; data: GameEventPush }
  | { type: 'room:event'; data: RoomEventPush }
  | { type: 'room:reaction'; data: ReactionPush }
  | { type: 'error'; data: ProtocolError }
  | { type: 'friends:snapshot'; data: { friends: { tag: string; status: FriendStatus }[] } }
  | { type: 'friends:presence'; data: { tag: string; status: FriendStatus } }
  | { type: 'friends:request'; data: { request: FriendRequestEntry } }
  | { type: 'friends:accepted'; data: { tag: string; nickname: string } }
  | { type: 'friends:removed'; data: { tag: string } }
  | { type: 'invite:received'; data: InvitePush }
  | { type: 'invite:expired'; data: { inviteId: string } }
  | { type: 'invite:cleared'; data: { inviteId: string } }
  | { type: 'guest:quota'; data: GuestQuota }

export type ServerMessage = AckMessage | PushMessage
