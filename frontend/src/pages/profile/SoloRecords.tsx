import { GameIcon } from '../../components/GameIcon'
import { gameUi } from '../../games/registry'
import { difficultyLabel, topicName, variantLabel } from '../../lib/solo'
import type { SoloRecordRow } from '../../types/protocol'
import { LoadError } from './ProfileSections'
import type { Load } from './useLoad'

const CHALLENGES: readonly string[] = ['guess_race', 'name_it', 'hangman']
const GUESS_LABELS: Record<string, string> = { scramble: 'Word Scramble', emoji: 'Emoji Guess', mixed: 'Mixed' }

/** "(Hard)", "5x5 Hard", or a challenge variant: the puzzle type, the Name It topic, "Word streak". */
function label(r: SoloRecordRow): string {
  if (r.gameId === 'guess_race') return `(${GUESS_LABELS[r.variant] ?? r.variant})`
  if (r.gameId === 'name_it') return `(${topicName(r.variant)})`
  if (r.gameId === 'hangman') return '(Word streak)'
  return r.variant.includes(':') ? variantLabel(r.variant) : `(${difficultyLabel(r.variant)})`
}

/** Solo records (PROTOCOL.md 16): played and won per game and difficulty. Registered players only. */
export function SoloRecordsSection({ records, onRetry }: { records: Load<SoloRecordRow[]>; onRetry: () => void }) {
  return (
    <section className="stack" aria-labelledby="solo-records-heading">
      <h2 id="solo-records-heading">Solo records</h2>
      {records.status === 'loading' && (
        <p className="muted" role="status">
          Loading your solo records…
        </p>
      )}
      {records.status === 'error' && <LoadError message={records.message} onRetry={onRetry} />}
      {records.status === 'ready' &&
        (records.data.length === 0 ? (
          <p className="muted profile__empty">Play alone to start your records</p>
        ) : (
          <ul className="bygame">
            {records.data.map((r) => {
              const game = gameUi(r.gameId)
              return (
                <li key={`${r.gameId}:${r.variant}`} className="bygame__row">
                  <span className="bygame__name">
                    <GameIcon id={r.gameId} size={20} />
                    {game?.name ?? r.gameId} {label(r)}
                  </span>
                  <span className="bygame__nums">
                    <span>{r.plays} played</span>
                    {CHALLENGES.includes(r.gameId) ? <span>Best: {r.bestScore}</span> : <span>{r.wins} won</span>}
                  </span>
                </li>
              )
            })}
          </ul>
        ))}
    </section>
  )
}
