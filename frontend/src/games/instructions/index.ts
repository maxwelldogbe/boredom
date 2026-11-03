import type { GameId } from '../../types/protocol'
import { hangmanInstructions } from './hangman'
import { guessRaceInstructions } from './guessRace'
import { dotsAndBoxesInstructions } from './dotsAndBoxes'
import { liarsDiceInstructions } from './liarsDice'
import { nameItInstructions } from './nameIt'
import { rpsInstructions } from './rps'
import { checkersInstructions } from './checkers'
import { connectFourInstructions } from './connectFour'
import { penaltyKickInstructions } from './penaltyKick'
import { ticTacToeInstructions } from './ticTacToe'
import type { GameInstructions, InstructionContext, InstructionEntry } from './types'

export const GAME_INSTRUCTIONS: Partial<Record<GameId, InstructionEntry>> = {
  rps: rpsInstructions,
  guess_race: guessRaceInstructions,
  hangman: hangmanInstructions,
  dots_and_boxes: dotsAndBoxesInstructions,
  liars_dice: liarsDiceInstructions,
  name_it: nameItInstructions,
  tic_tac_toe: ticTacToeInstructions,
  connect_four: connectFourInstructions,
  penalty_kick: penaltyKickInstructions,
  checkers: checkersInstructions,
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
