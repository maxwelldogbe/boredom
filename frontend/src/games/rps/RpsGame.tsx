import { useState } from 'react'
import { PlayerChip } from '../../components/PlayerChip'
import { TimerBar } from '../../components/TimerBar'
import { C } from '../../lib/constants'
import { nameOf, playerById } from '../../lib/players'
import type { RpsChoice, RpsMatch, RpsView } from '../../types/views'
import type { GameUiProps } from '../types'
import './rps.css'

const CHOICES: { id: RpsChoice; emoji: string; label: string }[] = [
  { id: 'rock', emoji: '✊', label: 'Rock' },
  { id: 'paper', emoji: '✋', label: 'Paper' },
  { id: 'scissors', emoji: '✌️', label: 'Scissors' },
]
const emojiOf = (c: RpsChoice | null) => CHOICES.find((x) => x.id === c)?.emoji ?? '⌛'
const labelOf = (c: RpsChoice | null) => CHOICES.find((x) => x.id === c)?.label ?? 'No pick'

/** Rock-Paper-Scissors (plan section 7). Renders only what the server's view says. */
export function RpsGame({ view, send, me, room }: GameUiProps<RpsView>) {
  const [sending, setSending] = useState<RpsChoice | null>(null)
  const match = view.myMatch !== null ? view.matches[view.myMatch] : null
  const opponent = match ? (match.a === me ? match.b : match.a) : null
  const oppName = nameOf(room, opponent)

  const pick = async (choice: RpsChoice) => {
    setSending(choice)
    await send({ type: 'pick', choice })
    setSending(null)
  }

  return (
    <div className="stack rps">
      <p className="muted">
        {view.mode === 'bracket' ? `Bracket round ${view.bracketRound} · ` : 'Duel · '}
        Best of {view.bestOf} (first to {Math.floor(view.bestOf / 2) + 1})
      </p>

      {match && opponent && view.phase !== 'matchOver' && view.phase !== 'done' && (
        <MatchScore match={match} me={me} opponentName={oppName} />
      )}

      {view.phase === 'picking' && match && opponent && (
        <>
          <TimerBar deadline={match.deadline} totalMs={C.RPS_PICK_TIMEOUT_MS} label="Time to pick" />
          <h2 className="rps__prompt">{view.myPick ? 'Locked in!' : 'Make your pick'}</h2>
          <div className="rps__choices">
            {CHOICES.map((c) => (
              <button
                key={c.id}
                type="button"
                className="rps__choice"
                aria-pressed={view.myPick === c.id || sending === c.id}
                disabled={view.myPick !== null || sending !== null}
                onClick={() => pick(c.id)}
              >
                <span className="rps__choice-emoji" aria-hidden="true">
                  {c.emoji}
                </span>
                <span>{c.label}</span>
              </button>
            ))}
          </div>
          <p className="rps__status" role="status">
            {view.myPick
              ? match.hasPicked[opponent]
                ? 'Both picked. Revealing…'
                : `⏳ Waiting for ${oppName}…`
              : match.hasPicked[opponent]
                ? `${oppName} has picked!`
                : `${oppName} is choosing…`}
          </p>
        </>
      )}

      {view.phase === 'reveal' && match?.lastReveal && opponent && (
        <Reveal match={match} me={me} opponent={opponent} oppName={oppName} />
      )}

      {view.phase === 'matchOver' && (
        <p className="rps__banner" role="status">
          {view.eliminated.includes(me)
            ? "😵 You're out. Watching the rest of the bracket."
            : match && match.b === null
              ? '🎟️ You have a bye this round. Waiting for the other matches…'
              : match?.winner === me
                ? '🎉 You won your match! Waiting for the other matches…'
                : '⏳ Waiting for the other matches…'}
        </p>
      )}

      {view.phase === 'done' && view.champion && (
        <p className="rps__banner rps__banner--win" role="status">
          🏆 {view.champion === me ? 'You are' : `${nameOf(room, view.champion)} is`} the champion!
        </p>
      )}

      {view.mode === 'bracket' && <BracketList view={view} me={me} room={room} />}
    </div>
  )
}

function MatchScore({ match, me, opponentName }: { match: RpsMatch; me: string; opponentName: string }) {
  const opp = match.a === me ? match.b : match.a
  return (
    <div className="rps__score" aria-label={`Score: you ${match.scores[me] ?? 0}, ${opponentName} ${opp ? match.scores[opp] ?? 0 : 0}`}>
      <span>You</span>
      <strong>
        {match.scores[me] ?? 0} – {opp ? match.scores[opp] ?? 0 : 0}
      </strong>
      <span>{opponentName}</span>
    </div>
  )
}

function Reveal({ match, me, opponent, oppName }: { match: RpsMatch; me: string; opponent: string; oppName: string }) {
  const reveal = match.lastReveal!
  const mine = reveal.picks[me] ?? null
  const theirs = reveal.picks[opponent] ?? null
  const result =
    match.winner === me
      ? '🏆 You win the match!'
      : match.winner === opponent
        ? `${oppName} wins the match.`
        : reveal.roundWinner === me
          ? '✅ You win the round!'
          : reveal.roundWinner === opponent
            ? `❌ ${oppName} wins the round.`
            : '🤝 Tie. Replay!'
  return (
    <div className="rps__reveal" role="status">
      <div className="rps__reveal-row">
        <figure>
          <span className="rps__big" aria-hidden="true">
            {emojiOf(mine)}
          </span>
          <figcaption>You: {labelOf(mine)}</figcaption>
        </figure>
        <span className="rps__vs">vs</span>
        <figure>
          <span className="rps__big" aria-hidden="true">
            {emojiOf(theirs)}
          </span>
          <figcaption>
            {oppName}: {labelOf(theirs)}
          </figcaption>
        </figure>
      </div>
      <p className="rps__banner">{result}</p>
    </div>
  )
}

function BracketList({ view, me, room }: Omit<GameUiProps<RpsView>, 'send'>) {
  return (
    <section className="card stack">
      <h3 className="section-title">Bracket round {view.bracketRound}</h3>
      <ul className="rps__bracket">
        {view.matches.map((m, i) => (
          <li key={i}>
            <PlayerChip player={playerById(room, m.a)} isMe={m.a === me} size="sm" extra={m.winner === m.a ? '✓ won' : undefined} />
            {m.b ? (
              <>
                <span className="rps__bracket-score">
                  {m.scores[m.a] ?? 0}–{m.scores[m.b] ?? 0}
                </span>
                <PlayerChip player={playerById(room, m.b)} isMe={m.b === me} size="sm" extra={m.winner === m.b ? '✓ won' : undefined} />
              </>
            ) : (
              <span className="muted">bye</span>
            )}
          </li>
        ))}
      </ul>
      {view.eliminated.length > 0 && (
        <p className="muted">Out: {view.eliminated.map((id) => nameOf(room, id, me)).join(', ')}</p>
      )}
    </section>
  )
}
