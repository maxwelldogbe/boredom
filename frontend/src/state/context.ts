import { createContext, useContext } from 'react'
import type { GameSocket } from '../lib/socket'
import type { GameId, PeekData, RoomPublic, SoloVariant } from '../types/protocol'
import type { RoomState } from './roomReducer'

export interface RoomActions {
  /** Create a room with the saved profile; resolves with the room code. */
  createRoom(): Promise<string>
  /** Join (or rejoin with the stored roomToken). */
  joinRoom(code: string): Promise<RoomPublic>
  peek(code: string): Promise<PeekData>
  /** Leave the room: marks the exit, sends room:leave, calls `go(to)` (navigate away), then
   *  clears the room state and its roomToken. */
  leaveRoom(to?: string, go?: (to: string) => void): Promise<void>
  quitGame(): Promise<void>
  selectGame(gameId: GameId, settings: Record<string, unknown>): Promise<void>
  startGame(): Promise<void>
  /** Lobby ready check (non-host players only). */
  setReady(ready: boolean): Promise<void>
  /** Send an emoji reaction (one of REACTION_EMOJIS). */
  react(emoji: string): Promise<void>
  playAgain(): Promise<void>
  /** Host: set the Brag coin stake (0 removes it). */
  setStake(amount: number): Promise<void>
  /** Join the stake or sit this round out. */
  stakeChoice(join: boolean): Promise<void>
  /** Start a solo game against a bot (registered players); resolves with the room code. */
  startSolo(gameId: GameId, variant: SoloVariant): Promise<string>
  /** A new game in the finished solo room. */
  soloAgain(): Promise<void>
  /** Close the solo room (nothing is recorded); the same order as leaveRoom. */
  soloQuit(to?: string, go?: (to: string) => void): Promise<void>
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
