import { seriesRules } from './ticTacToe'
import type { GameInstructions, InstructionContext } from './types'

export function connectFourInstructions(context: InstructionContext): GameInstructions {
  return {
    title: '🔴🔵 Connect Four',
    tagline: 'Drop discs and line up four.',
    goal: 'Connect four of your discs in a row.',
    steps: [
      'Tap a column to drop a disc.',
      'Discs fall to the lowest empty spot.',
      'Four in a row in any direction wins.',
      'A full board is a draw.',
    ],
    rules: seriesRules(context.constants.C4_TURN_MS),
    tips: [],
  }
}
