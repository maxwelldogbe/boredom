import type { GameInstructions, InstructionContext } from './types'

export function checkersInstructions(context: InstructionContext): GameInstructions {
  const { settings, constants } = context
  const rules = [
    `You have ${constants.CHECKERS_TURN_MS / 1000} seconds per turn. If time runs out, a random legal move is made for you.`,
    'The first move alternates between games.',
    `The game is a draw after ${constants.CHECKERS_DRAW_PLIES} turns with no capture or man move.`,
  ]
  if (settings.flyingKings === true) {
    rules.push('Flying kings: kings move any distance diagonally and can capture from a distance, landing on any empty square past the captured piece.')
  }
  if (settings.backwardCapture === true) {
    rules.push('Backward capture: men may also capture backward.')
  }
  rules.push('With more than 2 players it is a bracket: players are paired at random, winners move on, and everyone else can watch.')
  return {
    title: '⛀ Checkers',
    tagline: 'Jump, capture, and crown a king.',
    goal: 'Capture all enemy pieces or leave them with no moves.',
    steps: [
      'Take turns moving a piece one square diagonally forward.',
      'Jump over an enemy piece to capture it.',
      'Capturing is mandatory, and you must keep jumping if you can.',
      'Reach the far row to become a king (♛) that can move and capture backward too.',
      'You win when your opponent has no pieces or no moves.',
    ],
    rules,
    tips: ['Keep your back row home as long as you can.'],
  }
}
