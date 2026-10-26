import type { GameId } from '../../types/protocol'
import { hangmanInstructions } from './hangman'
import { guessRaceInstructions } from './guessRace'
import { dotsAndBoxesInstructions } from './dotsAndBoxes'
import { rpsInstructions } from './rps'
import type { GameInstructions, InstructionContext, InstructionEntry } from './types'

export const GAME_INSTRUCTIONS: Partial<Record<GameId, InstructionEntry>> = {
  rps: rpsInstructions,
  guess_race: guessRaceInstructions,
  hangman: hangmanInstructions,
  dots_and_boxes: dotsAndBoxesInstructions,
}

export function hasGameInstructions(id: GameId | null | undefined): boolean {
  return Boolean(id && GAME_INSTRUCTIONS[id])
}

export function gameInstructions(
  id: GameId | null | undefined,
  context?: InstructionContext,
): GameInstructions | null {
  if (!id) return null
  const entry = GAME_INSTRUCTIONS[id]
  if (!entry) return null
  if (typeof entry === 'function') return context ? entry(context) : null
  return entry
}
