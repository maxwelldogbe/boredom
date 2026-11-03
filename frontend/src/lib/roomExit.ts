/**
 * Room exits, in memory for this tab: where an intentional exit goes, and which rooms the
 * player sat in. The room route uses them to tell "I left" (go to the destination, silently)
 * from "the room vanished" (the closed screen); neither ever shows the invite landing.
 */
const leaving = new Map<string, string>() // room code -> destination
const seated = new Set<string>()

/** Set BEFORE sending leave or quit and before clearing room state. */
export function markLeaving(code: string, to: string): void {
  leaving.set(code.toUpperCase(), to)
}

/** Where an intentional exit from `code` goes, or null. */
export function leavingTo(code: string): string | null {
  return leaving.get(code.toUpperCase()) ?? null
}

/** The player holds a seat in `code` (a new seat cancels an old exit mark). */
export function markSeated(code: string): void {
  const upper = code.toUpperCase()
  seated.add(upper)
  leaving.delete(upper)
}

/** Whether the player sat in `code` during this visit. */
export function wasSeated(code: string): boolean {
  return seated.has(code.toUpperCase())
}

/** Test helper. */
export function resetRoomExits(): void {
  leaving.clear()
  seated.clear()
}
