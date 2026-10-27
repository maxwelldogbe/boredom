/** Typed access to fixtures captured from the real backend (see src/test/fixtures/*.json). */
import type { MeData, MyStats, RecentPlayer } from '../lib/account'
import type { GameEventPush, PeekData, ProtocolError, RoomPublic, SeatData } from '../types/protocol'
import type { GameViewPush } from '../types/views'
import dotsJson from './fixtures/dotsAndBoxes.json'
import guessRaceJson from './fixtures/guessRace.json'
import liarsDiceJson from './fixtures/liarsDice.json'
import hangmanJson from './fixtures/hangman.json'
import nameItJson from './fixtures/nameIt.json'
import profileJson from './fixtures/profile.json'
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
  /** Guess Race lobby: Ann ready, Bob and Dan not, Cat offline but ready (captured backend output). */
  roomLobbyReadySome: RoomPublic
  /** The same lobby with every online player ready. */
  roomLobbyReadyAll: RoomPublic
  gameOverEvent: GameEventPush
  errorPush: { type: 'error'; data: ProtocolError }
}

/** Captured /api/auth/me, /api/me/stats and /api/me/recent-players responses: Sam played 6 rps
 *  games with Ann and then 1 with Bob; Newbie has played nothing. */
export const profileFx = profileJson as unknown as {
  me: MeData
  stats: MyStats
  recentPlayers: { players: RecentPlayer[] }
  newMe: MeData
  statsEmpty: MyStats
  recentEmpty: { players: RecentPlayer[] }
  unauthorized: { error: { code: string; message: string } }
}

export const rpsFx = rpsJson as unknown as Record<keyof typeof rpsJson, Of<'rps'>>
export const guessRaceFx = guessRaceJson as unknown as Record<keyof typeof guessRaceJson, Of<'guess_race'>>
export const hangmanFx = hangmanJson as unknown as Record<keyof typeof hangmanJson, Of<'hangman'>>
export const dotsFx = dotsJson as unknown as Record<keyof typeof dotsJson, Of<'dots_and_boxes'>>
export const liarsDiceFx = liarsDiceJson as unknown as Record<keyof typeof liarsDiceJson, Of<'liars_dice'>>
export const nameItFx = nameItJson as unknown as Record<keyof typeof nameItJson, Of<'name_it'>>
