import { createContext, useContext } from 'react'
import type { GameSocket } from '../lib/socket'
import type { GameId, PeekData, RoomPublic } from '../types/protocol'
import type { RoomState } from './roomReducer'

export interface RoomActions {
  /** Create a room with the saved profile; resolves with the room code. */
  createRoom(): Promise<string>
  /** Join (or rejoin with the stored roomToken). */
  joinRoom(code: string): Promise<RoomPublic>
  peek(code: string): Promise<PeekData>
  leaveRoom(): Promise<void>
  quitGame(): Promise<void>
  selectGame(gameId: GameId, settings: Record<string, unknown>): Promise<void>
  startGame(): Promise<void>
  /** Lobby ready check (non-host players only). */
  setReady(ready: boolean): Promise<void>
  /** Send an emoji reaction (one of REACTION_EMOJIS). */
  react(emoji: string): Promise<void>
  playAgain(): Promise<void>
  sendAction(action: { type: string } & Record<string, unknown>): Promise<void>
  toast(message: string, tone?: 'info' | 'error'): void
  dismissToast(id: number): void
  socket: GameSocket
}

export const RoomStateContext = createContext<RoomState | null>(null)
export const RoomActionsContext = createContext<RoomActions | null>(null)

export function useRoomState(): RoomState {
  const value = useContext(RoomStateContext)
  if (!value) throw new Error('useRoomState must be used inside <RoomProvider>')
  return value
}

export function useRoomActions(): RoomActions {
  const value = useContext(RoomActionsContext)
  if (!value) throw new Error('useRoomActions must be used inside <RoomProvider>')
  return value
}
