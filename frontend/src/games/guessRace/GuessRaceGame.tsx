import { useRef, useState, type FormEvent } from 'react'
import { Button } from '../../components/Button'
import { PlayerCards } from '../../components/PlayerCards'
import { TimerBar } from '../../components/TimerBar'
import { C } from '../../lib/constants'
import { formatPoints } from '../../lib/format'
import { nameOf } from '../../lib/players'
import { useRemainingMs } from '../../state/useCountdown'
import type { GuessHint, GuessRaceView } from '../../types/views'
import type { GameUiProps } from '../types'
import './guessRace.css'

function hintText(hint: GuessHint): string {
  switch (hint.type) {
    case 'length':
      return `${hint.value} letters`
    case 'category':
      return `Category: ${hint.value}`
    case 'firstLetter':
      return `Starts with ${hint.value}`
  }
}

/** Guess Race (plan section 8): Word Scramble and Emoji Guess. Answers are checked by the server. */
export function GuessRaceGame({ view, send, me, room }: GameUiProps<GuessRaceView>) {
  const [text, setText] = useState('')
  const [sending, setSending] = useState(false)
  const input = useRef<HTMLInputElement>(null)
  const guessing = view.phase === 'guessing'
  const wrong = view.myLastGuess !== null && !view.myLastGuess.correct

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    const guess = text.trim()
    if (!guess || !guessing || sending) return
    setSending(true)
    await send({ type: 'guess', text: guess })
    setSending(false)
    setText('')
    input.current?.focus()
  }

  return (
    <div className="stack guess">
      <div className="guess__header">
        <span>
          Round {view.round}/{view.total}
        </span>
        <span className="muted">{view.kind === 'scramble' ? '🔤 Word Scramble' : '😀 Emoji Guess'}</span>
      </div>

      {guessing && <TimerBar deadline={view.roundEndsAt} totalMs={C.GUESS_ROUND_MS} label="Time left in round" />}

      <div className="guess__prompt" aria-label={view.kind === 'scramble' ? `Scrambled letters: ${view.prompt.split('').join(' ')}` : `Emojis: ${view.prompt}`}>
        {view.kind === 'scramble' ? (
          <div className="guess__tiles" aria-hidden="true">
            {view.prompt.split('').map((ch, i) => (
              <span key={i} className="guess__tile">
                {ch}
              </span>
            ))}
          </div>
        ) : (
          <div className="guess__emoji" aria-hidden="true">
            {view.prompt}
          </div>
        )}
      </div>

      {view.hints.length > 0 && (
        <ul className="guess__hints" aria-label="Hints">
          {view.hints.map((h) => (
            <li key={h.type} className="guess__hint">
              💡 {hintText(h)}
            </li>
          ))}
        </ul>
      )}

      {guessing && view.iSolved ? (
        <MySolve view={view} me={me} />
      ) : guessing ? (
        <form className="guess__form" onSubmit={submit}>
          <label htmlFor="guess-input" className="visually-hidden">
            Your guess
          </label>
          <input
            id="guess-input"
            ref={input}
            className={`field__input${wrong && !text ? ' guess__input--wrong' : ''}`}
            value={text}
            onChange={(e) => setText(e.target.value)}
            maxLength={C.GUESS_TEXT_MAX}
            placeholder="Type your guess"
            autoComplete="off"
            autoCorrect="off"
            autoCapitalize="off"
            spellCheck={false}
            enterKeyHint="send"
            autoFocus
          />
          <Button type="submit" disabled={!text.trim() || sending}>
            Guess
          </Button>
        </form>
      ) : (
        <RoundOver view={view} me={me} room={room} />
      )}

      {guessing && view.solvers.length > 0 && <Solvers view={view} me={me} room={room} />}

      {guessing && !view.iSolved && view.myLastGuess && (
        <p className={view.myLastGuess.correct ? 'guess__feedback guess__feedback--ok' : 'guess__feedback'} role="status">
          {view.myLastGuess.correct ? '✓ Correct!' : `✕ “${view.myLastGuess.text}” isn't it. Keep trying!`}
        </p>
      )}

      <PlayerCards
        room={room}
        me={me}
        entries={room.players.filter((p) => p.id in view.scores).map((p) => ({ id: p.id, value: formatPoints(view.scores[p.id]) }))}
      />
    </div>
  )
}

function RoundOver({ view, me, room }: Omit<GameUiProps<GuessRaceView>, 'send'>) {
  const remaining = useRemainingMs(view.revealEndsAt)
  return (
    <div className="card guess__over" role="status">
      <p className="muted">The answer was</p>
      <p className="guess__answer">{view.answer}</p>
      {view.solvers.length > 0 ? <Solvers view={view} me={me} room={room} /> : <p>⌛ Nobody got it this time.</p>}
      {view.phase === 'roundOver' && remaining !== null && (
        <p className="muted">
          {view.round < view.total ? 'Next round' : 'Results'} in {Math.ceil(remaining / 1000)}s…
        </p>
      )}
    </div>
  )
}

function ordinal(n: number): string {
  const suffix = n % 10 === 1 && n % 100 !== 11 ? 'st' : n % 10 === 2 && n % 100 !== 12 ? 'nd' : n % 10 === 3 && n % 100 !== 13 ? 'rd' : 'th'
  return `${n}${suffix}`
}

function MySolve({ view, me }: Pick<GameUiProps<GuessRaceView>, 'view' | 'me'>) {
  const mine = view.solvers.find((s) => s.playerId === me)
  return (
    <p className="guess__feedback guess__feedback--ok" role="status">
      ✓ Solved! You were {mine ? `${ordinal(mine.rank)} (+${mine.points})` : 'in'}. Waiting for the others…
    </p>
  )
}

/** Who has solved this round, in finishing order. Never shows the answer. */
function Solvers({ view, me, room }: Omit<GameUiProps<GuessRaceView>, 'send'>) {
  return (
    <ol className="guess__solvers" aria-label="Solved">
      {view.solvers.map((s) => (
        <li key={s.playerId}>
          🎉 {ordinal(s.rank)}: {nameOf(room, s.playerId, me)} <strong>+{s.points}</strong>
        </li>
      ))}
    </ol>
  )
}
