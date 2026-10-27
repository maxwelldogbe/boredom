import type { Player, ReadyCheck, RoomPublic } from '../../types/protocol'

/** The ready check, or null when there is none to show (no game picked, or an older server). */
export function readyCheck(room: RoomPublic): ReadyCheck | null {
  return room.selectedGame && room.readyCheck ? room.readyCheck : null
}

/** Online non-host players who have not tapped Ready, in seat order. */
export function notReady(room: RoomPublic): Player[] {
  return room.players.filter((p) => p.id !== room.hostId && p.online && p.ready !== true)
}

export function everyoneReady(check: ReadyCheck): boolean {
  return check.count >= check.total
}

/** "Ann", "Ann and Bob", "Ann, Bob and Cat", "Ann, Bob, Cat and 2 more". */
export function listNames(names: string[], max = 3): string {
  if (names.length <= 1) return names[0] ?? ''
  if (names.length > max) return `${names.slice(0, max).join(', ')} and ${names.length - max} more`
  return `${names.slice(0, -1).join(', ')} and ${names[names.length - 1]}`
}

/** The early-start confirmation body: "Ann and Bob aren't ready yet." */
export function notReadyMessage(players: Player[]): string {
  const names = listNames(players.map((p) => p.nickname))
  return `${names} ${players.length === 1 ? "isn't" : "aren't"} ready yet.`
}
