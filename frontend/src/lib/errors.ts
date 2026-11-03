/** Plain-language messages for request failures. */
import { C } from './constants'
import { RequestError } from './socket'

export function errorCode(err: unknown): string {
  return err instanceof RequestError ? err.code : 'UNKNOWN'
}

export function friendlyError(err: unknown, code?: string): string {
  if (!(err instanceof RequestError)) return 'Something went wrong. Please try again.'
  switch (err.code) {
    case 'ROOM_NOT_FOUND':
      return code
        ? `We couldn't find room ${code}. Check the code or ask the host for a new link.`
        : "We couldn't find that room."
    case 'ROOM_FULL':
      return `This room is full (${C.MAX_PLAYERS} players).`
    case 'GAME_IN_PROGRESS':
      return 'A game is in progress. You can join when it ends.'
    case 'DISCONNECTED':
      return "Can't reach the server. Check your connection and try again."
    case 'TIMEOUT':
      return 'The server is taking too long. It may be waking up; try again in a moment.'
    case 'RATE_LIMITED':
      return 'Slow down a little.'
    case 'REGISTERED_ONLY':
      return 'This game is for registered players.'
    case 'NOT_ENOUGH_BRAG':
      return `You need ${String(err.data?.stake ?? '')} Brag coins (you have ${String(err.data?.balance ?? 0)}). Beat a Hard bot to earn more.`
    case 'STAKE_NOT_AGREED':
      return err.message || 'Not enough players joined the stake.'
    case 'ALREADY_IN_GAME':
      return `You're still in a game in room ${String(err.data?.code ?? '')}.`
    case 'GAME_DISABLED':
      return 'This game is turned off right now. Pick another one.'
    default:
      return err.message || 'Something went wrong. Please try again.'
  }
}
