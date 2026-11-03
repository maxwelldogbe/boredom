/** How to play for the solo challenges (PROTOCOL.md 16.1); numbers come from the constants. */
import { C } from '../../lib/constants'
import type { GameId } from '../../types/protocol'
import type { GameInstructions } from '../instructions/types'

const sec = (ms: number) => ms / 1000

export const CHALLENGE_INSTRUCTIONS: Partial<Record<GameId, () => GameInstructions>> = {
  guess_race: () => ({
    title: '🔤 Guess Race: Beat the clock',
    tagline: 'Beat the clock.',
    goal: 'Solve as many puzzles as you can before time runs out.',
    steps: [
      `You have ${sec(C.SOLO_GUESS_RUN_MS)} seconds in total. Puzzles come one at a time.`,
      'Type your answer and send it. The faster you solve a puzzle, the more points it earns.',
      `Stuck? Tap Skip. It costs ${sec(C.SOLO_GUESS_SKIP_PENALTY_MS)} seconds.`,
      'Puzzles get harder as you solve more.',
      'When the clock hits zero, your score is saved. Try to beat your best!',
    ],
    rules: [
      `Clues appear after ${sec(C.GUESS_HINT1_MS)} and ${sec(C.GUESS_HINT2_MS)} seconds on a puzzle.`,
      `A puzzle you don't solve in ${sec(C.SOLO_GUESS_PUZZLE_MS)} seconds is skipped for free.`,
      "Capital letters, spaces, and punctuation don't matter.",
    ],
    tips: ['Guess early. Wrong guesses cost nothing.'],
  }),
  name_it: () => ({
    title: '🗣️ Name It: Streak',
    tagline: 'Streak.',
    goal: 'Name as many things in the topic as you can.',
    steps: [
      'Pick a topic, like fruits or countries.',
      `Type one answer at a time. You have ${sec(C.NAMEIT_TURN_MS)} seconds for each.`,
      'Every correct answer adds 1 to your streak.',
      "You can't repeat an answer.",
      `A wrong answer, a repeat, or running out of time costs a strike. After ${C.SOLO_NAMEIT_STRIKES} strikes, the run ends.`,
    ],
    rules: [
      'Answers are checked against our lists. Spelling must be right, but common alternate names are accepted.',
      "If a correct answer is missing from our list, we're sorry. We keep adding missing answers.",
    ],
    tips: ['Start with the easy ones before you run out of time.'],
  }),
  hangman: () => ({
    title: '🪢 Hangman: Word streak',
    tagline: 'Word streak.',
    goal: 'Solve as many words as you can before you run out of strikes.',
    steps: [
      'The computer picks a secret word.',
      'Pick letters one at a time. Correct letters appear in the word.',
      `Each wrong letter adds a part to the hangman. After ${C.HANGMAN_MAX_WRONG} wrong guesses the word is lost.`,
      `Losing a word costs a strike. After ${C.SOLO_HANGMAN_STRIKES} strikes, the run ends.`,
      'Solving a word adds to your streak. Words get longer and harder over time.',
    ],
    rules: ['There is no time limit.'],
    tips: ['Start with common letters like E, A, R, S, and T.'],
  }),
}

export function isChallenge(gameId: string | null | undefined): boolean {
  return Boolean(gameId && gameId in CHALLENGE_INSTRUCTIONS)
}
