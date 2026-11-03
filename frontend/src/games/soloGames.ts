import type { GameId } from '../types/protocol'

/** Games with a bot for solo play (PROTOCOL.md 16), in picker order. */
export const SOLO_BOT_GAMES: readonly GameId[] = ['tic_tac_toe', 'connect_four', 'dots_and_boxes', 'penalty_kick']

/** Bot games added in part 3: their tiles show the record of the last-used variant. */
export const SOLO_TILE_RECORD_GAMES: readonly GameId[] = ['dots_and_boxes', 'penalty_kick']

export const DOTS_GAME: GameId = 'dots_and_boxes'

/** Extra how-to-play lines for a game in a solo room. */
export const SOLO_EXTRA_LINES: Partial<Record<GameId, string>> = {
  dots_and_boxes: 'The first move is random and alternates each game.',
  penalty_kick: 'You will shoot and keep goal in turn. The bot can be beaten by quick, controlled swipes.',
}

/** Settings a solo game runs with (PROTOCOL.md 16), for its instructions. */
export function soloSettings(gameId: GameId, size: number): Record<string, unknown> {
  if (gameId === DOTS_GAME) return { size }
  if (gameId === 'penalty_kick') return { kicksPerPlayer: 5, keeperSpeed: 'normal' }
  return { bestOf: 1 }
}

/** Solo challenges (PROTOCOL.md 16.1): one player, a score to beat. */
export const SOLO_CHALLENGES: readonly { id: GameId; title: string }[] = [
  { id: 'guess_race', title: 'Guess Race: Beat the clock' },
  { id: 'name_it', title: 'Name It: Streak' },
  { id: 'hangman', title: 'Hangman: Word streak' },
]
