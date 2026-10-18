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

export interface ProtocolError {
  code: ErrorCode
  message: string
}

/** Profile as sent to the server (`room:create` / `room:join`). */
export interface WireProfile {
  id: string
  nickname: string
  emoji: string
  color: string
  type: 'guest' | 'registered'
}

export interface Player {
  id: string
  profileId: string
  nickname: string
  emoji: string
  color: string
  online: boolean
  joinedAt: number
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
}

export interface GameResult {
  playerId: string
  placement: number
  points: number
}

/** Ack data of room:create and room:join. */
export interface SeatData {
  playerId: string
  roomToken: string
  room: RoomPublic
}

export interface PeekData {
  exists: boolean
  hostNickname: string | null
  playerCount: number
  status: RoomStatus | null
}

type Empty = Record<string, never>

/** Every request type with its payload and its ack `data`. */
export interface RequestMap {
  'room:create': { payload: { profile: WireProfile }; data: SeatData }
  'room:join': {
    payload: { code: string; profile: WireProfile; roomToken?: string }
    data: SeatData
  }
  'room:peek': { payload: { code: string }; data: PeekData }
  'room:leave': { payload: Empty; data: Empty }
  'room:selectGame': {
    payload: { gameId: GameId; settings: Record<string, unknown> }
    data: Empty
  }
  'game:start': { payload: Empty; data: Empty }
  'game:action': { payload: { type: string } & Record<string, unknown>; data: Empty }
  'game:playAgain': { payload: Empty; data: Empty }
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

export interface GameOverData {
  results: GameResult[]
}

export type PushMessage =
  | { type: 'room:state'; data: RoomPublic }
  | { type: 'game:view'; data: GameViewPush }
  | { type: 'game:event'; data: GameEventPush }
  | { type: 'error'; data: ProtocolError }

export type ServerMessage = AckMessage | PushMessage
