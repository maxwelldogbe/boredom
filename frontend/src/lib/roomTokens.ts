/** roomToken per room code (reclaims the seat after a refresh or dropped connection). */
import { readItem, removeItem, writeItem } from './storage'

const KEY = 'partypack.roomTokens'

function readAll(): Record<string, string> {
  try {
    const parsed: unknown = JSON.parse(readItem(KEY) ?? '{}')
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      return Object.fromEntries(
        Object.entries(parsed).filter((e): e is [string, string] => typeof e[1] === 'string'),
      )
    }
  } catch {
    // corrupt value: start over
  }
  return {}
}

export function getRoomToken(code: string): string | null {
  return readAll()[code.toUpperCase()] ?? null
}

export function setRoomToken(code: string, token: string): void {
  writeItem(KEY, JSON.stringify({ ...readAll(), [code.toUpperCase()]: token }))
}

export function clearRoomToken(code: string): void {
  const all = readAll()
  delete all[code.toUpperCase()]
  if (Object.keys(all).length === 0) removeItem(KEY)
  else writeItem(KEY, JSON.stringify(all))
}
