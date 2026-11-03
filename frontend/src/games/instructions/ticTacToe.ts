import type { GameInstructions, InstructionContext } from './types'

/** Rules lines shared by the series board games (tic-tac-toe, connect four). */
export function seriesRules(turnMs: number): string[] {
  return [
    `You have ${turnMs / 1000} seconds per turn. If time runs out, a random move is made for you.`,
    'The first move alternates between games.',
    'With more than 2 players it is a bracket: players are paired at random, winners move on, and everyone else can watch.',
  ]
}

export function winsNeeded(context: InstructionContext): number {
  return Math.floor(Number(context.settings.bestOf ?? 3) / 2) + 1
}

export function ticTacToeInstructions(context: InstructionContext): GameInstructions {
  const wins = winsNeeded(context)
  return {
    title: '❌⭕ Tic-Tac-Toe',
    tagline: 'The classic three in a row.',
    goal: 'Get three of your marks in a row.',
    steps: [
      'Take turns placing a mark.',
      'The first to get 3 in a row (across, down, or diagonal) wins the game.',
      'In a draw the game is replayed.',
      `The first to win ${wins} ${wins === 1 ? 'game' : 'games'} wins the match.`,
    ],
    rules: seriesRules(context.constants.TTT_TURN_MS),
    tips: [],
  }
}
