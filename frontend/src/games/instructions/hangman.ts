import type { GameInstructions, InstructionContext } from './types'

type HangmanMode = 'group' | 'duel'

function modeFrom(settings: Record<string, unknown>): HangmanMode {
  return settings.mode === 'duel' ? 'duel' : 'group'
}

export function hangmanInstructions(context: InstructionContext): GameInstructions {
  const mode = modeFrom(context.settings)
  const { constants } = context
  const wordMin = constants.HANGMAN_WORD_MIN
  const wordMax = constants.HANGMAN_WORD_MAX
  const pot = constants.HANGMAN_POT
  const cost = constants.HANGMAN_WRONG_COST
  const maxWrong = constants.HANGMAN_MAX_WRONG
  const setterSeconds = constants.HANGMAN_SET_WORD_MS / 1000
  const flagSeconds = constants.HANGMAN_FLAG_WINDOW_MS / 1000
  const voteSeconds = constants.HANGMAN_VOTE_MS / 1000
  const exampleWrongGuesses = 2
  const exampleGuessers = pot - exampleWrongGuesses * cost
  const exampleSetter = exampleWrongGuesses * cost
  const rules = [
    'Words must be real words with letters only: no numbers, spaces, or symbols.',
    `The setter has ${setterSeconds} seconds to enter a word. If they run out of time, their turn is skipped.`,
    'A letter can only be guessed once.',
    "The setter can't guess in their own round.",
  ]

  return {
    title: '🪢 Hangman Duel',
    tagline: 'One player sets the word. The others try to save the hangman.',
    goal:
      mode === 'duel'
        ? "Guess your opponent's secret word before the drawing is complete."
        : 'Work together to guess the secret word before the drawing is complete.',
    steps: [
      `One player is the setter. They secretly type a word of ${wordMin} to ${wordMax} letters. They can add an optional hint, like a category.`,
      mode === 'duel'
        ? 'The other player picks letters one at a time.'
        : 'Everyone else picks letters. You all share the same guesses, so work together.',
      'If the letter is in the word, it appears in every spot where it belongs.',
      `If the letter is not in the word, the hangman gets another part. After ${maxWrong} wrong guesses, the drawing is complete and the guessers lose the round.`,
      'Each round has a different setter, so everyone gets a turn setting a word and a turn guessing.',
      'After every player has been the setter once, the player with the most points wins.',
    ],
    rules,
    points: [
      `Every round is worth ${pot} points, whatever the word is.`,
      `If the word is guessed, the guesser(s) get ${pot} minus ${cost} for each wrong guess. The setter gets ${cost} for each wrong guess.`,
      `If the drawing is completed, the setter gets all ${pot} points.`,
      ...(mode === 'group' ? ["The guessers' points are shared equally."] : []),
      `Example: the word is guessed after ${exampleWrongGuesses} wrong guesses. Guessers get ${exampleGuessers}, and the setter gets ${exampleSetter}.`,
      'Long words are no easier to score on. Only wrong guesses matter.',
    ],
    ...(context.playerCount >= 3
      ? {
          challenge: [
            `Think the setter used a made-up word? After the round, you have ${flagSeconds} seconds to flag it.`,
            `Then the guessers vote for ${voteSeconds} seconds. If most vote that it isn't a real word, the setter gets 0 points and the guessers share all ${pot} points.`,
            'Ties keep the word valid.',
          ],
        }
      : {}),
    tips: [
      'Start with common letters like E, A, R, S, and T.',
      'As setter, pick a word that is tricky but fair. A made-up word can get flagged and cost you all your points.',
      'Use the hint wisely. A category can help the guessers a lot.',
    ],
  }
}
