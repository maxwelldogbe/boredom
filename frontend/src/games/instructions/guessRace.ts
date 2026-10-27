import type { GameInstructions, InstructionContext } from './types'

type GuessMode = 'scramble' | 'emoji' | 'mixed'

function modeFrom(settings: Record<string, unknown>): GuessMode {
  const content = settings.content
  return content === 'scramble' || content === 'emoji' || content === 'mixed' ? content : 'mixed'
}

function pointsByPlace(playerCount: number, first: number, step: number, floor: number) {
  const places = Math.max(1, Math.min(playerCount, 3))
  return Array.from({ length: places }, (_, index) => Math.max(floor, first - step * index))
}

function pointsRule(playerCount: number, first: number, step: number, floor: number) {
  const [rank1, rank2, rank3] = pointsByPlace(playerCount, first, step, floor)
  if (playerCount <= 2) {
    return `First to solve earns ${rank1} points, second earns ${rank2}. Each place earns ${step} fewer points, but never less than ${floor}. If you don't solve it, you earn 0.`
  }
  return `First to solve earns ${rank1} points, second earns ${rank2}, third earns ${rank3}, and so on. Each place earns ${step} fewer points, but never less than ${floor}. If you don't solve it, you earn 0.`
}

function cluesRule(mode: GuessMode, hint1: number, hint2: number) {
  if (mode === 'scramble') {
    return `Clues appear as time passes. After ${hint1} seconds you get a clue: the number of letters for scrambled words. After ${hint2} seconds you also see the first letter.`
  }
  if (mode === 'emoji') {
    return `Clues appear as time passes. After ${hint1} seconds you get a clue: the category for emoji puzzles. After ${hint2} seconds you also see the first letter.`
  }
  return `Clues appear as time passes. After ${hint1} seconds you get a clue: the category for emoji puzzles, or the number of letters for scrambled words. After ${hint2} seconds you also see the first letter.`
}

export function guessRaceInstructions(context: InstructionContext): GameInstructions {
  const mode = modeFrom(context.settings)
  const rounds = Number(context.settings.rounds) || 10
  const roundSeconds = context.constants.GUESS_ROUND_MS / 1000
  const windowSeconds = context.constants.GUESS_SOLVED_WINDOW_MS / 1000
  const hint1 = context.constants.GUESS_HINT1_MS / 1000
  const hint2 = context.constants.GUESS_HINT2_MS / 1000
  const first = context.constants.GUESS_RANK_POINTS_FIRST
  const step = context.constants.GUESS_RANK_POINTS_STEP
  const floor = context.constants.GUESS_RANK_POINTS_FLOOR

  const goals: Record<GuessMode, string> = {
    scramble: 'Unscramble the letters to find the hidden word before everyone else.',
    emoji: 'Work out the word or title hidden in the emojis before everyone else.',
    mixed: 'Solve each puzzle before everyone else. Some are scrambled words and some are emoji puzzles.',
  }

  const firstStep: Record<GuessMode, string> = {
    scramble: 'A word appears with its letters mixed up. For example, PLEPA is APPLE.',
    emoji: 'A row of emojis appears. Together they stand for a word, a movie, or a phrase.',
    mixed: 'A puzzle appears for everyone at the same time: either a scrambled word or a row of emojis.',
  }

  const tipsByMode: Record<GuessMode, string[]> = {
    scramble: ['Look for common endings like -ING, -ED, and -ER, and pairs like TH and SH.'],
    emoji: ['Think about movies, food, places, and everyday phrases. The category clue helps a lot.'],
    mixed: [
      'Look for common endings like -ING, -ED, and -ER, and pairs like TH and SH.',
      'Think about movies, food, places, and everyday phrases. The category clue helps a lot.',
    ],
  }

  const referenceByMode: Record<GuessMode, { left: string; verb: string; right: string }[]> = {
    scramble: [{ left: 'PLEPA', verb: '=', right: 'APPLE' }],
    emoji: [
      { left: '🌧️🏹', verb: '=', right: 'Rainbow' },
      { left: '🦁👑', verb: '=', right: 'The Lion King' },
    ],
    mixed: [
      { left: 'PLEPA', verb: '=', right: 'APPLE' },
      { left: '🌧️🏹', verb: '=', right: 'Rainbow' },
      { left: '🦁👑', verb: '=', right: 'The Lion King' },
    ],
  }

  const rules = [
    `You have ${roundSeconds} seconds for each puzzle.`,
    `Once someone solves it, everyone else has ${windowSeconds} seconds left to solve it too.`,
    pointsRule(context.playerCount, first, step, floor),
    cluesRule(mode, hint1, hint2),
    "Capital letters, spaces, and punctuation don't matter.",
    ...(mode === 'emoji' || mode === 'mixed' ? ['Starting with "The" is optional.'] : []),
    'If players are tied at the end, they share the same place.',
  ]

  return {
    title: '⚡ Guess Race',
    tagline: 'Be the fastest to crack the puzzle.',
    goal: goals[mode],
    steps: [
      firstStep[mode],
      'Type your guess and press Enter or tap Send. You can guess as many times as you like.',
      'Everyone who solves the puzzle earns points. The faster you solve it, the more points you get.',
      `As soon as someone solves it, the timer drops to ${windowSeconds} seconds for everyone else. The round ends when that time is up, when every player has solved it, or when the ${roundSeconds} seconds run out. The answer is shown, then the next puzzle starts.`,
      `After ${rounds} puzzles, the player with the most points wins.`,
    ],
    rules,
    tips: [...tipsByMode[mode], "Guess early. A wrong guess doesn't cost you points."],
    reference: referenceByMode[mode],
  }
}
