/** Per-game views (`game:view` → data.view), mirroring core/PROTOCOL.md section 7. */

import type { SoloResult } from './protocol'

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

export interface GuessSolver {
  playerId: string
  rank: number
  points: number
}

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
  solvers: GuessSolver[]
  iSolved: boolean
  answer: string | null
  myLastGuess: { text: string; correct: boolean } | null
}

export interface HangmanView {
  phase: 'setting' | 'guessing' | 'roundOver' | 'flagVote' | 'done'
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
  award: Record<string, number>
  scores: Record<string, number>
  pot: number
  wrongCost: number
  flagUntil: number | null
  canFlag: boolean
  flag: {
    flaggerId: string
    deadline: number
    voterIds: string[]
    votedCount: number
    canVote: boolean
    hasVoted: boolean
  } | null
}

export interface DotsView {
  phase: 'playing' | 'done'
  /** Solo rooms only (PROTOCOL.md 16): the outcome once the game ends. */
  soloResult?: SoloResult | null
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

export interface DiceBid {
  playerId: string
  quantity: number
  face: number
}

export interface DiceReveal {
  round: number
  call: 'liar' | 'spotOn'
  callerId: string
  bid: DiceBid
  dice: Record<string, number[]>
  actual: number
  loserId: string | null
  gainerId: string | null
  eliminatedId: string | null
  auto: boolean
}

export interface LiarsDiceView {
  phase: 'bidding' | 'reveal' | 'done'
  round: number
  order: string[]
  myDice: number[]
  diceCounts: Record<string, number>
  totalDice: number
  eliminated: string[]
  currentPlayerId: string | null
  isYourTurn: boolean
  currentBid: DiceBid | null
  history: (DiceBid & { auto: boolean })[]
  settings: { startingDice: number; wildOnes: boolean; spotOn: boolean }
  deadline: number | null
  lastReveal: DiceReveal | null
}

export interface NameItChallenge {
  answerIndex: number
  answererId: string
  challengerId: string
  text: string
  deadline: number
  voterIds: string[]
  votedCount: number
  canVote: boolean
  hasVoted: boolean
}

export interface NameItView {
  phase: 'topicSelect' | 'turn' | 'challenge' | 'done'
  topic: string | null
  topicChooserId: string | null
  isTopicChooser: boolean
  suggestions: string[]
  topicDeadline: number | null
  order: string[]
  alive: string[]
  eliminated: string[]
  currentPlayerId: string | null
  isYourTurn: boolean
  turnDeadline: number | null
  pausedMs: number | null
  used: { playerId: string; text: string }[]
  challengeWindow: { answerIndex: number; until: number } | null
  challengeWindowMs: number
  canChallenge: boolean
  challenge: NameItChallenge | null
  lastElimination: { playerId: string; reason: 'timeout' | 'duplicate' | 'challenge'; text: string | null } | null
  settings: { turnSeconds: number; challenges: boolean; allowCustomTopics: boolean }
}

/** One pairing of a series game (PROTOCOL.md 7.7). `b` is null for a bye. */
export interface SeriesMatch<G = unknown> {
  id: string
  a: string
  b: string | null
  phase: 'playing' | 'over'
  wins: Record<string, number>
  gameNo: number
  draws: number
  winner: string | null
  reason: 'bye' | 'score' | 'forfeit' | 'afk' | 'coinFlip' | null
  coinFlip: boolean
  lastGame: { gameNo: number; result: 'winner' | 'draw'; winner: string | null; game: G } | null
}

/** The shared shell of every series game (tic-tac-toe, connect four, …); `G` is the game view. */
export interface SeriesView<G> {
  phase: 'playing' | 'waiting' | 'out' | 'done'
  role: 'player' | 'spectator'
  bestOf: number
  winsNeeded: number
  bracketRound: number
  matches: SeriesMatch<G>[]
  liveMatches: string[]
  match: (SeriesMatch<G> & { game: G }) | null
  watching: string | null
  alive: string[]
  eliminated: string[]
  champion: string | null
  /** Solo rooms only (PROTOCOL.md 16): the outcome once the game ends. */
  soloResult?: SoloResult | null
}

export interface TicTacToeGame {
  board: ('X' | 'O' | null)[]
  marks: Record<string, 'X' | 'O'>
  firstMover: string
  turn: string | null
  turnDeadline: number | null
  lastMove: number | null
  winner: string | null
  winningCells: number[] | null
  isYourTurn?: boolean
  legalMoves?: number[]
}

export interface ConnectFourGame {
  board: (1 | 2 | null)[][]
  seats: Record<string, 1 | 2>
  firstMover: string
  turn: string | null
  turnDeadline: number | null
  lastMove: { row: number; column: number; playerId: string } | null
  winner: string | null
  winningCells: [number, number][] | null
  isYourTurn?: boolean
  legalMoves?: number[]
}

/** A point in the goal plane: x 0 (left post) to 1 (right post), y 0 (ground) to 1 (crossbar). */
export interface GoalPoint {
  x: number
  y: number
}

export type PenaltyOutcome = 'goal' | 'saved' | 'wide' | 'over' | 'post' | 'fizzled'

/** A resolved kick (PROTOCOL.md 7.10). */
export interface PenaltyKick {
  kick: number
  shooter: string
  keeper: string
  to: GoalPoint
  power: number
  keeperSpot: GoalPoint
  dive: GoalPoint | null
  outcome: PenaltyOutcome
}

/** The ball in the air (flight and result phases). `to` is the real aim. */
export interface PenaltyFlight {
  launchAt: number
  arriveAt: number
  graceMs: number
  ball: { from: GoalPoint; to: GoalPoint; power: number }
  /** Where the keeper stood when the ball was kicked; the dive starts here. */
  keeperSpot: GoalPoint
  dive: (GoalPoint & { receivedAt: number }) | null
}

export type KeeperSpeed = 'easy' | 'normal' | 'hard'

export interface PenaltyGame {
  kicksPerPlayer: number
  keeperSpeed: KeeperSpeed
  firstMover: string
  phase: 'aiming' | 'flight' | 'result' | 'over'
  shooter: string | null
  keeper: string | null
  kickNo: number
  round: number
  suddenDeath: boolean
  scores: Record<string, number>
  kicks: PenaltyKick[]
  lastKick: PenaltyKick | null
  turnDeadline: number | null
  /** Aiming only: the keeper's patrol keyframes (epoch ms), straight lines between them. */
  keeperPath: (GoalPoint & { at: number })[] | null
  flight: PenaltyFlight | null
  outcome: PenaltyOutcome | null
  resultUntil: number | null
  winner: string | null
  yourRole?: 'shooter' | 'keeper' | null
}

export type Square = [number, number]

export interface CheckersPiece {
  seat: 1 | 2
  king: boolean
}

export interface CheckersMove {
  from: Square
  to: Square
  captures: Square[]
}

/** PROTOCOL.md 7.11. `legalMoves` only for the player to move, already filtered by the server. */
export interface CheckersGame {
  board: (CheckersPiece | null)[][]
  seats: Record<string, 1 | 2>
  firstMover: string
  turn: string | null
  turnDeadline: number | null
  forcedPiece: Square | null
  lastMove: (CheckersMove & { playerId: string; crowned: boolean }) | null
  quietPlies: number
  drawPlies: number
  flyingKings: boolean
  backwardCapture: boolean
  winner: string | null
  draw: boolean
  isYourTurn?: boolean
  legalMoves?: CheckersMove[]
}

export type TicTacToeView = SeriesView<TicTacToeGame>
export type PenaltyKickView = SeriesView<PenaltyGame>
export type CheckersView = SeriesView<CheckersGame>
export type ConnectFourView = SeriesView<ConnectFourGame>

/** `game:view` push data, discriminated by gameId (games with a backend today). */
export type GameViewPush =
  | { gameId: 'rps'; view: RpsView; serverNow: number }
  | { gameId: 'guess_race'; view: GuessRaceView; serverNow: number }
  | { gameId: 'hangman'; view: HangmanView; serverNow: number }
  | { gameId: 'dots_and_boxes'; view: DotsView; serverNow: number }
  | { gameId: 'liars_dice'; view: LiarsDiceView; serverNow: number }
  | { gameId: 'name_it'; view: NameItView; serverNow: number }
  | { gameId: 'tic_tac_toe'; view: TicTacToeView; serverNow: number }
  | { gameId: 'connect_four'; view: ConnectFourView; serverNow: number }
  | { gameId: 'penalty_kick'; view: PenaltyKickView; serverNow: number }
  | { gameId: 'checkers'; view: CheckersView; serverNow: number }

// ----- solo challenges (PROTOCOL.md 16.1): rendered by the solo room, not the game registry -----

export interface ChallengeResult {
  outcome: 'run_over'
  score: number
  detail: Record<string, unknown>
  /** Null when saving failed. */
  best: number | null
  isNewBest: boolean
  record: { plays: number; bestScore: number } | null
}

export interface GuessRunView {
  phase: 'playing' | 'done'
  content: 'scramble' | 'emoji' | 'mixed'
  kind: 'scramble' | 'emoji'
  prompt: string | null
  hints: GuessHint[]
  score: number
  solved: number
  skipped: number
  level: number
  runEndsAt: number
  puzzleStartedAt: number
  puzzleEndsAt: number
  lastResult: { correct: boolean; points: number; answerIfSkipped: string | null } | null
  soloResult?: ChallengeResult | null
}

export interface NameItRunView {
  phase: 'playing' | 'done'
  topic: { id: string; name: string; emoji: string }
  streak: number
  strikes: number
  maxStrikes: number
  accepted: string[]
  turnEndsAt: number | null
  lastResult: { kind: 'correct' | 'wrong' | 'repeat' | 'timeout' } | null
  completed: boolean
  soloResult?: ChallengeResult | null
}

export interface HangmanRunView {
  phase: 'guessing' | 'lost' | 'done'
  mask: (string | null)[]
  guessed: { correct: string[]; wrong: string[] }
  wrongCount: number
  maxWrong: number
  strikes: number
  maxStrikes: number
  solved: number
  level: number
  wordNumber: number
  revealedWord: string | null
  revealUntil: number | null
  soloResult?: ChallengeResult | null
}

export type ChallengePush =
  | { gameId: 'solo_guess_run'; view: GuessRunView; serverNow: number }
  | { gameId: 'solo_name_it'; view: NameItRunView; serverNow: number }
  | { gameId: 'solo_hangman'; view: HangmanRunView; serverNow: number }
