import type { GameInstructions, InstructionContext } from './types'

export function penaltyKickInstructions(context: InstructionContext): GameInstructions {
  const kicks = Number(context.settings.kicksPerPlayer ?? 5)
  const aimSeconds = context.constants.PENALTY_AIM_MS / 1000
  return {
    title: '⚽ Penalty Kick',
    tagline: 'Shoot, save, and read your opponent.',
    goal: 'Score more goals than your opponent.',
    steps: [
      'Each kick, one player shoots and the other keeps goal. Roles swap every kick.',
      'Shooter: swipe from the ball toward the spot you want. Where your swipe ends is where the ball goes. A faster flick means a harder shot.',
      'The keeper moves around the goal while the shooter aims and stops when the ball is kicked.',
      'Keeper: swipe to dive as soon as the ball is kicked. A longer swipe reaches further.',
      "If the ball hits the keeper, or the diving keeper's hands reach it, it is saved.",
      `${kicks} kicks each, then sudden death if tied.`,
    ],
    rules: [
      `You have ${aimSeconds} seconds to shoot (a mild shot is taken if you run out of time).`,
      'Very weak shots stop short.',
      'Wild hard shots can miss the goal.',
      'The ball can hit the post.',
      "Late dives don't count.",
    ],
    tips: ['Corners beat keepers, but hit them with a controlled flick.'],
  }
}
