/**
 * Game UI registry keyed by backend game id: picker metadata plus the screen for each game.
 */
import type { GameId } from '../types/protocol'
import { CheckersGame } from './checkers/CheckersGame'
import { ConnectFourGame } from './connectFour/ConnectFourGame'
import { DotsGame } from './dotsAndBoxes/DotsGame'
import { GuessRaceGame } from './guessRace/GuessRaceGame'
import { HangmanGame } from './hangman/HangmanGame'
import { LiarsDiceGame } from './liarsDice/LiarsDiceGame'
import { NameItGame } from './nameIt/NameItGame'
import { PenaltyKickGame } from './penaltyKick/PenaltyKickGame'
import { RpsGame } from './rps/RpsGame'
import { TicTacToeGame } from './ticTacToe/TicTacToeGame'
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
  dots_and_boxes: {
    id: 'dots_and_boxes',
    name: 'Dots and Boxes',
    icon: '🔲',
    description: 'Take turns drawing lines. Close a box to claim it and go again.',
    minPlayers: 2,
    maxPlayers: 4,
    settings: [
      { key: 'size', label: 'Board size', options: [4, 5, 6, 7].map((n) => ({ value: n, label: `${n} × ${n} boxes` })) },
    ],
    Component: DotsGame,
  },
  liars_dice: {
    id: 'liars_dice',
    name: "Liar's Dice",
    icon: '🎲',
    description: 'Bid on everyone\'s hidden dice. Call a bluff, lose a die. Last one standing wins.',
    minPlayers: 2,
    maxPlayers: 6,
    settings: [
      { key: 'startingDice', label: 'Starting dice', options: [3, 4, 5, 6].map((n) => ({ value: n, label: `${n} dice` })) },
      { key: 'wildOnes', label: 'Ones are wild', options: [{ value: false, label: 'Off' }, { value: true, label: 'On' }] },
      { key: 'spotOn', label: 'Spot-on calls', options: [{ value: false, label: 'Off' }, { value: true, label: 'On' }] },
    ],
    Component: LiarsDiceGame,
  },
  name_it: {
    id: 'name_it',
    name: 'Name It Survival',
    icon: '🗣️',
    description: 'Name things in a topic, one at a time. Repeat, stall or get voted down and you are out.',
    minPlayers: 3,
    maxPlayers: 10,
    settings: [
      { key: 'turnSeconds', label: 'Time per turn', options: [5, 10, 15, 20, 30].map((n) => ({ value: n, label: `${n} seconds` })) },
      { key: 'challenges', label: 'Challenges', options: [{ value: true, label: 'On' }, { value: false, label: 'Off' }] },
      {
        key: 'allowCustomTopics',
        label: 'Typed topics',
        options: [
          { value: false, label: 'Off (pick from suggestions)' },
          { value: true, label: 'On' },
        ],
      },
    ],
    Component: NameItGame,
  },
  tic_tac_toe: {
    id: 'tic_tac_toe',
    name: 'Tic-Tac-Toe',
    icon: '❌',
    description: 'Three in a row wins. Duel or knockout bracket, everyone else watches.',
    minPlayers: 2,
    maxPlayers: 10,
    settings: [{ key: 'bestOf', label: 'Match length', options: [1, 3, 5].map((n) => ({ value: n, label: `Best of ${n}` })) }],
    Component: TicTacToeGame,
  },
  connect_four: {
    id: 'connect_four',
    name: 'Connect Four',
    icon: '🔴',
    description: 'Drop discs, line up four. Duel or knockout bracket, everyone else watches.',
    minPlayers: 2,
    maxPlayers: 10,
    settings: [{ key: 'bestOf', label: 'Match length', options: [1, 3, 5].map((n) => ({ value: n, label: `Best of ${n}` })) }],
    Component: ConnectFourGame,
  },
  penalty_kick: {
    id: 'penalty_kick',
    name: 'Penalty Kick',
    icon: '⚽',
    description: 'Swipe to shoot, swipe to save. Duel or knockout bracket, everyone else watches.',
    minPlayers: 2,
    maxPlayers: 10,
    settings: [
      { key: 'kicksPerPlayer', label: 'Kicks each', options: [3, 5].map((n) => ({ value: n, label: `${n} kicks` })) },
      {
        key: 'keeperSpeed',
        label: 'Keeper speed',
        options: [
          { value: 'easy', label: 'Easy' },
          { value: 'normal', label: 'Normal' },
          { value: 'hard', label: 'Hard' },
        ],
      },
    ],
    Component: PenaltyKickGame,
  },
  checkers: {
    id: 'checkers',
    name: 'Checkers',
    icon: '⛀',
    description: 'Jump, capture, crown a king. Duel or knockout bracket, everyone else watches.',
    minPlayers: 2,
    maxPlayers: 10,
    settings: [
      { key: 'bestOf', label: 'Match length', options: [1, 3].map((n) => ({ value: n, label: `Best of ${n}` })) },
      { key: 'flyingKings', label: 'Flying kings', options: [{ value: false, label: 'Off' }, { value: true, label: 'On' }] },
      { key: 'backwardCapture', label: 'Men capture backward', options: [{ value: false, label: 'Off' }, { value: true, label: 'On' }] },
    ],
    Component: CheckersGame,
  },
}

export const GAME_LIST = Object.values(GAME_UIS)

export function gameUi(id: GameId | null | undefined): GameUi<ImplementedGameId> | null {
  return id && id in GAME_UIS ? (GAME_UIS[id as ImplementedGameId] as GameUi<ImplementedGameId>) : null
}
