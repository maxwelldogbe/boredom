/** Registered-only games (PROTOCOL.md 12). The list lives only in shared/constants.json. */
import type { GameId, Player, RoomPublic } from '../types/protocol'
import { C } from './constants'

const REGISTERED_ONLY: readonly string[] = C.REGISTERED_ONLY_GAMES

export function isRegisteredOnly(id: GameId | null | undefined): boolean {
  return Boolean(id && REGISTERED_ONLY.includes(id))
}

/** Guests never see registered-only games; registered players see every game. */
export function canSeeGame(id: GameId, registered: boolean): boolean {
  return registered || !isRegisteredOnly(id)
}

export function isRegisteredSeat(room: RoomPublic, me: string): boolean {
  return room.players.some((p) => p.id === me && p.type === 'registered')
}

/** Guests who sit out the selected registered-only game. */
export function blockedPlayers(room: RoomPublic): Player[] {
  return room.players.filter((p) => p.registeredOnlyBlocked === true)
}

export function isBlocked(room: RoomPublic, me: string): boolean {
  return room.players.some((p) => p.id === me && p.registeredOnlyBlocked === true)
}
