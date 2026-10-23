/** Per-game views (`game:view` → data.view), mirroring core/PROTOCOL.md section 7. */

export type RpsChoice = 'rock' | 'paper' | 'scissors'

export interface RpsMatch {
  a: string
  b: string | null
  phase: 'picking' | 'reveal' | 'over'
  round: number
  scores: Record<string, number>
  hasPicked: Record<string, boolean>
  deadline: number | null
  winner: string | null
  lastReveal: {
    round: number
    picks: Record<string, RpsChoice | null>
    roundWinner: string | null
  } | null
}

export interface RpsView {
  phase: 'picking' | 'reveal' | 'matchOver' | 'done'
  mode: 'duel' | 'bracket'
  bestOf: 3 | 5
  bracketRound: number
  myMatch: number | null
  myPick: RpsChoice | null
  matches: RpsMatch[]
  alive: string[]
  eliminated: string[]
  champion: string | null
}

export type GuessHint =
  | { type: 'length'; value: number }
  | { type: 'category'; value: string }
  | { type: 'firstLetter'; value: string }

export interface GuessRaceView {
  phase: 'guessing' | 'roundOver' | 'done'
  round: number
  total: number
  kind: 'scramble' | 'emoji'
  prompt: string
  hints: GuessHint[]
  roundStartedAt: number
  roundEndsAt: number
  revealEndsAt: number | null
  scores: Record<string, number>
  roundWinner: string | null
  roundPoints: number
  answer: string | null
  myLastGuess: { text: string; correct: boolean } | null
}

export interface HangmanView {
  phase: 'setting' | 'guessing' | 'roundOver' | 'done'
  round: number
  total: number
  setterId: string
  isSetter: boolean
  mask: (string | null)[]
  word: string | null
  hint: string | null
  guessed: string[]
  wrong: string[]
  wrongCount: number
  maxWrong: number
  deadline: number | null
  result: 'guessers' | 'setter' | 'skipped' | null
  scores: Record<string, number>
}

export interface DotsView {
  phase: 'playing' | 'done'
  size: number
  order: string[]
  currentPlayerId: string | null
  isYourTurn: boolean
  lines: Record<string, string>
  boxes: (string | null)[][]
  scores: Record<string, number>
  lastMove: {
    lineId: string
    playerId: string
    boxes: [number, number][]
    auto: 'timeout' | 'offline' | null
  } | null
  turnDeadline: number | null
}

/** `game:view` push data, discriminated by gameId (games with a backend today). */
export type GameViewPush =
  | { gameId: 'rps'; view: RpsView; serverNow: number }
  | { gameId: 'guess_race'; view: GuessRaceView; serverNow: number }
  | { gameId: 'hangman'; view: HangmanView; serverNow: number }
  | { gameId: 'dots_and_boxes'; view: DotsView; serverNow: number }
