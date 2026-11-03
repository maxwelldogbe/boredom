/** Solo games against a bot (PROTOCOL.md 16): the games, difficulty labels and saved choices. */
import type { GameInstructions } from '../games/instructions/types'
import { SOLO_EXTRA_LINES } from '../games/soloGames'
import type { GameId, SoloDifficulty, SoloRecordRow } from '../types/protocol'
import { apiCall } from './account'
import { C } from './constants'
import { readItem, writeItem } from './storage'

export const SOLO_DIFFICULTIES = C.SOLO_DIFFICULTIES as readonly SoloDifficulty[]

const DIFFICULTY_KEY = 'partypack.soloDifficulty'
const DOTS_SIZE_KEY = 'partypack.soloDotsSize'
const GUESS_KEY = 'partypack.soloGuess'
const TOPIC_KEY = 'partypack.soloTopic'
export const GUESS_CONTENTS = [
  { value: 'scramble', label: 'Word Scramble' },
  { value: 'emoji', label: 'Emoji Guess' },
  { value: 'mixed', label: 'Mixed' },
] as const
export type GuessContent = (typeof GUESS_CONTENTS)[number]['value']
export const RANDOM_TOPIC = 'random'
export const DOTS_SIZES = [4, 5, 6] as const
const SEEN_KEY = 'partypack.soloHowToSeen'

export function difficultyLabel(difficulty: string): string {
  return difficulty.charAt(0).toUpperCase() + difficulty.slice(1)
}

export function savedDifficulty(): SoloDifficulty {
  const value = readItem(DIFFICULTY_KEY)
  return SOLO_DIFFICULTIES.find((d) => d === value) ?? 'medium'
}

export function saveDifficulty(difficulty: SoloDifficulty): void {
  writeItem(DIFFICULTY_KEY, difficulty)
}

export function savedDotsSize(): number {
  const value = Number(readItem(DOTS_SIZE_KEY))
  return DOTS_SIZES.find((s) => s === value) ?? 5
}

export function saveDotsSize(size: number): void {
  writeItem(DOTS_SIZE_KEY, String(size))
}

export function savedGuessContent(): GuessContent {
  const value = readItem(GUESS_KEY)
  return GUESS_CONTENTS.find((c) => c.value === value)?.value ?? 'mixed'
}

export function saveGuessContent(content: GuessContent): void {
  writeItem(GUESS_KEY, content)
}

export function savedTopic(): string {
  const value = readItem(TOPIC_KEY)
  return C.SOLO_NAMEIT_TOPICS.some((t) => t.id === value) ? (value as string) : RANDOM_TOPIC
}

export function saveTopic(topic: string): void {
  writeItem(TOPIC_KEY, topic)
}

export interface SoloChoice {
  difficulty: SoloDifficulty
  size: number
  content: GuessContent
  topic: string
}

/** The SoloRecord variant string for a choice: the difficulty, "<difficulty>:<n>x<n>" for Dots
 *  and Boxes, the content type, the topic, or "classic" for Hangman. Null for a random topic. */
export function recordVariant(gameId: GameId, choice: SoloChoice): string | null {
  if (gameId === 'dots_and_boxes') return `${choice.difficulty}:${choice.size}x${choice.size}`
  if (gameId === 'guess_race') return choice.content
  if (gameId === 'name_it') return choice.topic === RANDOM_TOPIC ? null : choice.topic
  if (gameId === 'hangman') return 'classic'
  return choice.difficulty
}

/** The player's best score in a game over all its variants (challenges), or null. */
export function bestOf(records: SoloRecordRow[], gameId: GameId, variant?: string | null): number | null {
  const rows = records.filter((r) => r.gameId === gameId && r.plays > 0 && (variant === undefined || r.variant === variant))
  return rows.length ? Math.max(...rows.map((r) => r.bestScore)) : null
}

/** A Name It topic's name, or the id if unknown. */
export function topicName(id: string): string {
  return C.SOLO_NAMEIT_TOPICS.find((t) => t.id === id)?.name ?? id
}

/** "5x5 Hard" for a Dots and Boxes variant, "Hard" for the others. */
export function variantLabel(variant: string): string {
  const [difficulty, size] = variant.split(':')
  return size ? `${size} ${difficultyLabel(difficulty)}` : difficultyLabel(difficulty)
}

function seenGames(): string[] {
  try {
    const parsed: unknown = JSON.parse(readItem(SEEN_KEY) ?? '[]')
    return Array.isArray(parsed) ? parsed.filter((x): x is string => typeof x === 'string') : []
  } catch {
    return []
  }
}

/** Whether the game's instructions were already shown from its solo sheet. */
export function soloHowToSeen(gameId: GameId): boolean {
  return seenGames().includes(gameId)
}

export function markSoloHowToSeen(gameId: GameId): void {
  const seen = seenGames()
  if (!seen.includes(gameId)) writeItem(SEEN_KEY, JSON.stringify([...seen, gameId]))
}

/** The game's instructions with the solo lines added. */
export function withBotLine(content: GameInstructions, difficulty: string, gameId?: GameId | null): GameInstructions {
  const extra = gameId ? SOLO_EXTRA_LINES[gameId] : undefined
  const lines = [`You are playing against a Bot (${difficultyLabel(difficulty)}).`, ...(extra ? [extra] : [])]
  return { ...content, rules: [...lines, ...content.rules] }
}

export function fetchSoloRecords(token: string): Promise<SoloRecordRow[]> {
  return apiCall('GET', '/api/solo/records', undefined, token)
}
