/**
 * Game UI registry keyed by backend game id. Only games the backend implements are listed;
 * dots_and_boxes, liars_dice and name_it are pending (no backend yet) and stay hidden.
 */
import type { GameId } from '../types/protocol'
import { GuessRaceGame } from './guessRace/GuessRaceGame'
import { HangmanGame } from './hangman/HangmanGame'
import { RpsGame } from './rps/RpsGame'
import type { GameUi, ImplementedGameId } from './types'

type Registry = { [G in ImplementedGameId]: GameUi<G> }

export const GAME_UIS: Registry = {
  rps: {
    id: 'rps',
    name: 'Rock-Paper-Scissors',
    icon: '✊',
    description: 'Pick in secret, reveal together. Duel or knockout bracket.',
    minPlayers: 2,
    maxPlayers: 10,
    settings: [
      { key: 'bestOf', label: 'Match length', options: [{ value: 3, label: 'Best of 3' }, { value: 5, label: 'Best of 5' }] },
      {
        key: 'mode',
        label: 'Mode',
        options: [
          { value: 'duel', label: 'Duel (exactly 2 players)' },
          { value: 'bracket', label: 'Bracket (3+ players)' },
        ],
      },
    ],
    Component: RpsGame,
  },
  guess_race: {
    id: 'guess_race',
    name: 'Guess Race',
    icon: '⚡',
    description: 'Unscramble words or decode emojis. Fastest correct guess wins.',
    minPlayers: 2,
    maxPlayers: 10,
    settings: [
      {
        key: 'content',
        label: 'Puzzles',
        options: [
          { value: 'mixed', label: 'Mixed' },
          { value: 'scramble', label: 'Word Scramble' },
          { value: 'emoji', label: 'Emoji Guess' },
        ],
      },
      { key: 'rounds', label: 'Rounds', options: [5, 10, 15].map((n) => ({ value: n, label: `${n} rounds` })) },
      {
        key: 'difficulty',
        label: 'Word difficulty',
        options: [
          { value: 'mixed', label: 'Any' },
          { value: 'easy', label: 'Easy' },
          { value: 'medium', label: 'Medium' },
          { value: 'hard', label: 'Hard' },
        ],
      },
    ],
    Component: GuessRaceGame,
  },
  hangman: {
    id: 'hangman',
    name: 'Hangman Duel',
    icon: '🪢',
    description: 'One player hides a word, everyone else guesses letters. Everyone sets once.',
    minPlayers: 2,
    maxPlayers: 10,
    settings: [
      {
        key: 'mode',
        label: 'Mode',
        options: [
          { value: 'group', label: 'Group' },
          { value: 'duel', label: 'Duel (exactly 2 players)' },
        ],
      },
    ],
    Component: HangmanGame,
  },
}

export const GAME_LIST = Object.values(GAME_UIS)

export function gameUi(id: GameId | null | undefined): GameUi<ImplementedGameId> | null {
  return id && id in GAME_UIS ? (GAME_UIS[id as ImplementedGameId] as GameUi<ImplementedGameId>) : null
}
