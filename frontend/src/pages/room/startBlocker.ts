import { gameUi } from '../../games/registry'
import type { RoomPublic } from '../../types/protocol'

/** Reason Start is disabled, or null when the host can start. */
export function startBlocker(room: RoomPublic): string | null {
  const game = gameUi(room.selectedGame)
  if (!game) return 'Pick a game first.'
  const count = room.players.length
  if (count < game.minPlayers) return `Needs at least ${game.minPlayers} players.`
  if (count > game.maxPlayers) return `${game.name} allows at most ${game.maxPlayers} players.`
  return null
}
