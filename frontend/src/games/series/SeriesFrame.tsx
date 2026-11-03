import type { ReactNode } from 'react'
import { Button } from '../../components/Button'
import { C } from '../../lib/constants'
import { nameOf, playerById } from '../../lib/players'
import type { RoomPublic } from '../../types/protocol'
import type { SeriesMatch, SeriesView } from '../../types/views'
import type { GameAction } from '../types'
import { MatchCards } from './MatchCards'
import './series.css'

interface SeriesFrameProps<G> {
  view: SeriesView<G>
  me: string
  room: RoomPublic
  send: (action: GameAction) => Promise<boolean>
  /** Whose move it is in the shown game (highlighted card). */
  activeId: string | null
  /** The board of the shown match. */
  children: ReactNode
  /** Card scores; default: games won in the match. */
  scores?: Record<string, number>
  scoreLabel?: (score: number) => string
  /** Hide the series line (games with one game per match). */
  single?: boolean
  /** Solo rooms: show "Bot is thinking…" on the bot's turn (games with their own label opt out). */
  thinking?: boolean
}

const gamesWon = (n: number) => `${n} ${n === 1 ? 'game' : 'games'} won`

/** Everything around a series game's board: watch banner, cards, series line, bracket.
 *  In a solo room (PROTOCOL.md 16) only the cards, the bot's thinking note and the board. */
export function SeriesFrame<G>({ view, me, room, send, activeId, children, scores, scoreLabel = gamesWon, single = false, thinking = true }: SeriesFrameProps<G>) {
  const match = view.match
  const solo = Boolean(room.solo)
  const spectating = !solo && view.role === 'spectator' && view.phase !== 'done'
  const plain = single || solo
  const botThinking = solo && thinking && view.phase === 'playing' && Boolean(activeId) && Boolean(playerById(room, activeId).bot)
  return (
    <div className="stack series">
      {spectating && match && <WatchBanner view={view} match={match} me={me} room={room} send={send} />}
      {spectating && !match && <p className="muted series__note">Waiting for the other matches to finish…</p>}
      {!solo && view.phase === 'done' && view.champion && (
        <p className="series__note" role="status">
          🏆 {nameOf(room, view.champion, me)} {view.champion === me ? 'win' : 'wins'}!
        </p>
      )}
      {match && match.b && (
        <>
          <MatchCards
            room={room}
            me={me}
            seats={[match.a, match.b]}
            scores={scores ?? match.wins}
            scoreLabel={scoreLabel}
            activeId={activeId}
          />
          {!plain && <SeriesLine view={view} match={match} me={me} room={room} />}
          {match.coinFlip && (
            <p className="series__notice" role="status">
              🪙 Decided by coin flip after {C.MATCH_MAX_DRAWS} draws
            </p>
          )}
          {!plain && <LastGameNote match={match} me={me} room={room} />}
          {botThinking && (
            <p className="series__note solo__thinking" role="status">
              Bot is thinking…
            </p>
          )}
          {children}
        </>
      )}
      {!solo && view.matches.length > 1 && <BracketList view={view} shownId={match?.id ?? null} me={me} room={room} />}
    </div>
  )
}

function SeriesLine<G>({ view, match, me, room }: { view: SeriesView<G>; match: SeriesMatch<G>; me: string; room: RoomPublic }) {
  const b = match.b as string
  const played = (match.wins[match.a] ?? 0) + (match.wins[b] ?? 0)
  const gameNo = Math.min(played + (match.phase === 'playing' ? 1 : 0), view.bestOf) || 1
  return (
    <p className="series__line">
      <span>
        Game {gameNo} of {view.bestOf}
      </span>
      <span aria-label={`Games won: ${nameOf(room, match.a, me)} ${match.wins[match.a] ?? 0}, ${nameOf(room, b, me)} ${match.wins[b] ?? 0}`}>
        {nameOf(room, match.a, me)} {match.wins[match.a] ?? 0} – {match.wins[b] ?? 0} {nameOf(room, b, me)}
      </span>
    </p>
  )
}

function LastGameNote<G>({ match, me, room }: { match: SeriesMatch<G>; me: string; room: RoomPublic }) {
  const last = match.lastGame
  if (!last || match.phase !== 'playing' || last.gameNo !== match.gameNo - 1) return null
  return (
    <p className="muted series__note" role="status">
      {last.result === 'draw'
        ? 'Last game was a draw. It is replayed with the other player starting.'
        : `Last game: ${nameOf(room, last.winner, me)} won.`}
    </p>
  )
}

function WatchBanner<G>({
  view,
  match,
  me,
  room,
  send,
}: {
  view: SeriesView<G>
  match: SeriesMatch<G>
  me: string
  room: RoomPublic
  send: (action: GameAction) => Promise<boolean>
}) {
  const others = view.matches.filter((m) => view.liveMatches.includes(m.id) && m.id !== match.id)
  const vs = (m: SeriesMatch<G>) => `${nameOf(room, m.a, me)} vs ${nameOf(room, m.b, me)}`
  return (
    <div className="series__watch" role="status">
      <p className="series__watch-title">
        👀 Watching {vs(match)}
      </p>
      {others.length > 0 && (
        <div className="series__switch" role="group" aria-label="Switch match">
          {others.map((m) => (
            <Button key={m.id} variant="secondary" onClick={() => void send({ type: 'watch', matchId: m.id })}>
              Watch {vs(m)}
            </Button>
          ))}
        </div>
      )}
    </div>
  )
}

function BracketList<G>({ view, shownId, me, room }: { view: SeriesView<G>; shownId: string | null; me: string; room: RoomPublic }) {
  return (
    <section className="series__bracket">
      <h3 className="series__bracket-title">Round {view.bracketRound}</h3>
      <ol className="series__matches" aria-label={`Bracket, round ${view.bracketRound}`}>
        {view.matches.map((m) => {
          const current = m.id === shownId
          return (
            <li key={m.id} className={`series__match${current ? ' series__match--current' : ''}`} aria-current={current ? 'true' : undefined}>
              {m.b === null ? (
                <span>
                  {nameOf(room, m.a, me)} <span className="muted">bye</span>
                </span>
              ) : (
                <span>
                  {m.winner === m.a && '✓ '}
                  {nameOf(room, m.a, me)} {m.wins[m.a] ?? 0} – {m.wins[m.b] ?? 0} {nameOf(room, m.b, me)}
                  {m.winner === m.b && ' ✓'}
                </span>
              )}
              {m.phase === 'playing' && <span className="series__live">live</span>}
            </li>
          )
        })}
      </ol>
      {view.eliminated.length > 0 && (
        <p className="muted">Out: {view.eliminated.map((id) => nameOf(room, id, me)).join(', ')}</p>
      )}
    </section>
  )
}
