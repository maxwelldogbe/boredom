import type { GameInstructions } from './types'

export const rpsInstructions: GameInstructions = {
  title: '✊✋✌️ Rock Paper Scissors',
  tagline: 'A quick duel. Outsmart your opponent.',
  goal: 'Win more rounds than your opponent to win the match.',
  steps: [
    'Everyone picks Rock, Paper, or Scissors in secret.',
    'When both players have picked, the choices are revealed at the same time.',
    'The winner of the round gets a point. A tie means you play the round again.',
    'The first player to win {roundsToWin} rounds wins the match.',
  ],
  rules: [
    "You have {pickSeconds} seconds to pick. If you don't pick in time, you lose the round.",
    'If you disconnect for {offlineSeconds} seconds, you forfeit the match.',
    'With 3 or more players, it is a tournament: players are paired at random, winners move on, and the last player standing wins. If the number of players is odd, one player gets a free pass (a bye) to the next round.',
  ],
  tips: ["Don't be predictable. Players often repeat their last choice.", 'Watch the timer. Pick before it runs out.'],
  reference: [
    { left: '✊ Rock', verb: 'beats', right: '✌️ Scissors' },
    { left: '✌️ Scissors', verb: 'beats', right: '✋ Paper' },
    { left: '✋ Paper', verb: 'beats', right: '✊ Rock' },
  ],
}
