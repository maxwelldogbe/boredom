/** Pure reducer for connection, room, game view, events and toasts. */
import type { SocketStatus } from '../lib/socket'
import type { GameEventPush, GameResult, RoomPublic } from '../types/protocol'
import type { GameViewPush } from '../types/views'

export interface Toast {
  id: number
  message: string
  tone: 'info' | 'error'
}

export interface RoomState {
  connection: SocketStatus
  room: RoomPublic | null
  playerId: string | null
  game: GameViewPush | null
  /** serverNow − client clock when the latest view arrived (ms). */
  clockOffset: number
  events: GameEventPush[]
  lastResults: GameResult[] | null
  toasts: Toast[]
  /** Set when the server says this socket lost its seat (closed room, another tab). */
  seatLost: string | null
}

export type RoomAction =
  | { type: 'connection'; status: SocketStatus }
  | { type: 'seated'; playerId: string; room: RoomPublic }
  | { type: 'roomState'; room: RoomPublic }
  | { type: 'gameView'; push: GameViewPush; receivedAt: number }
  | { type: 'gameEvent'; event: GameEventPush }
  | { type: 'left' }
  | { type: 'seatLost'; message: string }
  | { type: 'toast'; toast: Toast }
  | { type: 'dismissToast'; id: number }

export const MAX_EVENTS = 20

export const initialRoomState: RoomState = {
  connection: 'disconnected',
  room: null,
  playerId: null,
  game: null,
  clockOffset: 0,
  events: [],
  lastResults: null,
  toasts: [],
  seatLost: null,
}

function withRoom(state: RoomState, room: RoomPublic): RoomState {
  const startedNewGame = room.status === 'playing' && state.room?.status !== 'playing'
  return {
    ...state,
    room,
    game: room.status === 'lobby' || startedNewGame ? null : state.game,
    lastResults: startedNewGame ? null : state.lastResults,
    events: startedNewGame ? [] : state.events,
  }
}

export function roomReducer(state: RoomState, action: RoomAction): RoomState {
  switch (action.type) {
    case 'connection':
      return { ...state, connection: action.status }
    case 'seated':
      return { ...withRoom(state, action.room), playerId: action.playerId, seatLost: null }
    case 'roomState':
      return withRoom(state, action.room)
    case 'gameView':
      return {
        ...state,
        game: action.push,
        clockOffset: action.push.serverNow - action.receivedAt,
      }
    case 'gameEvent': {
      const events = [...state.events, action.event].slice(-MAX_EVENTS)
      const results =
        action.event.kind === 'gameOver'
          ? ((action.event.data as { results?: GameResult[] }).results ?? null)
          : state.lastResults
      return { ...state, events, lastResults: results }
    }
    case 'left':
      return { ...initialRoomState, connection: state.connection, toasts: state.toasts }
    case 'seatLost':
      return {
        ...initialRoomState,
        connection: state.connection,
        toasts: state.toasts,
        seatLost: action.message,
      }
    case 'toast':
      return { ...state, toasts: [...state.toasts, action.toast].slice(-3) }
    case 'dismissToast':
      return { ...state, toasts: state.toasts.filter((t) => t.id !== action.id) }
  }
}
