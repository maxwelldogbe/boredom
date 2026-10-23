import { C } from '../../lib/constants'
import type { RoomPublic } from '../../types/protocol'

/**
 * One distinct colour per player, in turn order. Each player keeps their profile colour
 * unless someone earlier already has it; then they get the first unused palette colour.
 */
export function playerColors(order: string[], room: RoomPublic): Record<string, string> {
  const used = new Set<string>()
  const colors: Record<string, string> = {}
  for (const id of order) {
    const own = room.players.find((p) => p.id === id)?.color.toUpperCase()
    const color = own && !used.has(own) ? own : C.PLAYER_COLORS.find((c) => !used.has(c.toUpperCase()))!
    used.add(color.toUpperCase())
    colors[id] = color
  }
  return colors
}
