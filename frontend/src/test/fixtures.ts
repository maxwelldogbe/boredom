/** Typed access to fixtures captured from the real backend (see src/test/fixtures/*.json). */
import type { MeData, MyStats, RecentPlayer } from '../lib/account'
import type { FriendProfile, FriendsOverview } from '../lib/social'
import type {
  FriendRequestEntry,
  FriendStatus,
  GameEventPush,
  InvitePush,
  PeekData,
  PresenceMode,
  ProtocolError,
  RoomPublic,
  SeatData,
} from '../types/protocol'
import type { GameViewPush } from '../types/views'
import dotsJson from './fixtures/dotsAndBoxes.json'
import guessRaceJson from './fixtures/guessRace.json'
import liarsDiceJson from './fixtures/liarsDice.json'
import hangmanJson from './fixtures/hangman.json'
import nameItJson from './fixtures/nameIt.json'
import profileJson from './fixtures/profile.json'
import roomJson from './fixtures/room.json'
import socialJson from './fixtures/social.json'
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

type ApiErrorBody = { error: { code: string; message: string } }

/** Captured friends, presence, invite and admin-report traffic (captured from the real backend):
 *  Sam's friends are Ann (online), Bob (hosting a lobby) and Cat (offline); Dan asked Sam;
 *  Sam asked Eve and blocked Zed. */
export const socialFx = socialJson as unknown as {
  emptyOverview: FriendsOverview
  overview: FriendsOverview
  settings: { presence: PresenceMode }
  settingsBusy: { presence: PresenceMode }
  acceptAck: { status: 'friends' }
  requestSent: { status: 'requested' }
  blockAck: { ok: true }
  requestErrors: Record<string, { status: number; body: ApiErrorBody }>
  helloAck: { presence: PresenceMode }
  helloUnauthorized: ProtocolError
  snapshot: { friends: { tag: string; status: FriendStatus }[] }
  friendProfile: FriendProfile
  friendProfileForbidden: ApiErrorBody
  presenceBusy: { tag: string; status: FriendStatus }
  presenceOnline: { tag: string; status: FriendStatus }
  acceptedPush: { tag: string; nickname: string }
  requestPush: { request: FriendRequestEntry }
  removedPush: { tag: string }
  recentPlayers: { players: RecentPlayer[] }
  inviteSendAck: Record<string, never>
  inviteReceived: InvitePush
  inviteSendErrors: Record<'RATE_LIMITED' | 'TARGET_UNAVAILABLE' | 'NOT_FRIENDS', ProtocolError>
  inviteAcceptAck: { code: string }
  inviteCleared: { inviteId: string }
  inviteAcceptErrors: { INVITE_INVALID: ProtocolError }
  inviteExpired: { inviteId: string }
  inviteAcceptExpired: ProtocolError
  roomWithAccounts: RoomPublic
  roomSeats: { sam: string; ann: string; guest: string }
  byPlayer: { requestAck: ProtocolError; guestRequestError: ProtocolError; reportGuestAck: Record<string, never> }
  // eslint-disable-next-line @typescript-eslint/no-explicit-any -- typed by the admin page tests
  admin: any
  tags: Record<string, string>
}
