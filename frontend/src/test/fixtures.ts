/** Typed access to fixtures captured from the real backend (see src/test/fixtures/*.json). */
import type { GameEventPush, PeekData, ProtocolError, RoomPublic, SeatData } from '../types/protocol'
import type { GameViewPush } from '../types/views'
import dotsJson from './fixtures/dotsAndBoxes.json'
import guessRaceJson from './fixtures/guessRace.json'
import liarsDiceJson from './fixtures/liarsDice.json'
import hangmanJson from './fixtures/hangman.json'
import nameItJson from './fixtures/nameIt.json'
import roomJson from './fixtures/room.json'
import rpsJson from './fixtures/rps.json'

/** A captured game:view with the receiving player's id and their room state at that moment. */
export interface ViewFixture<P extends GameViewPush = GameViewPush> {
  me: string
  room: RoomPublic
  push: P
}

type Of<G extends GameViewPush['gameId']> = ViewFixture<Extract<GameViewPush, { gameId: G }>>

export const roomFx = roomJson as unknown as {
  seatAck: SeatData
  peekExists: PeekData
  peekMissing: PeekData
  roomLobby2: RoomPublic
  roomLobby3Bracket: RoomPublic
  roomFinished: RoomPublic
  roomPlayingWithLeaver: RoomPublic
  gameOverEvent: GameEventPush
  errorPush: { type: 'error'; data: ProtocolError }
}

export const rpsFx = rpsJson as unknown as Record<keyof typeof rpsJson, Of<'rps'>>
export const guessRaceFx = guessRaceJson as unknown as Record<keyof typeof guessRaceJson, Of<'guess_race'>>
export const hangmanFx = hangmanJson as unknown as Record<keyof typeof hangmanJson, Of<'hangman'>>
export const dotsFx = dotsJson as unknown as Record<keyof typeof dotsJson, Of<'dots_and_boxes'>>
export const liarsDiceFx = liarsDiceJson as unknown as Record<keyof typeof liarsDiceJson, Of<'liars_dice'>>
export const nameItFx = nameItJson as unknown as Record<keyof typeof nameItJson, Of<'name_it'>>
