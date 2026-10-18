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
    default:
      return err.message || 'Something went wrong. Please try again.'
  }
}
