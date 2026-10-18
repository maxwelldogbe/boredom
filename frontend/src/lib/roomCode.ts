import { C } from './constants'

/** True if `code` has the room-code format (length and alphabet, no I or O). */
export function isRoomCode(code: string): boolean {
  return (
    code.length === C.ROOM_CODE_LENGTH && [...code].every((ch) => C.ROOM_CODE_ALPHABET.includes(ch))
  )
}

/** Uppercase and keep letters only (what the code boxes accept). */
export function cleanCodeInput(raw: string): string {
  return raw.toUpperCase().replace(/[^A-Z]/g, '')
}
