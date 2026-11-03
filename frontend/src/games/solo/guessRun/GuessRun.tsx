import { useRef, useState, type FormEvent } from 'react'
import { Button } from '../../../components/Button'
import { TimerBar } from '../../../components/TimerBar'
import { C } from '../../../lib/constants'
import { useRoomState } from '../../../state/context'
import { useNow, useRemainingMs } from '../../../state/useCountdown'
import type { GuessHint, GuessRunView } from '../../../types/views'
import type { GameAction } from '../../types'
import '../../guessRace/guessRace.css'
import '../solo.css'

const FLASH_MS = 1500

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

/** Guess Race "Beat the clock" (PROTOCOL.md 16.1). The server keeps the clock and the answers. */
export function GuessRun({ view, send }: { view: GuessRunView; send: (action: GameAction) => Promise<boolean> }) {
  const [text, setText] = useState('')
  const [sending, setSending] = useState(false)
  const input = useRef<HTMLInputElement>(null)
  const { clockOffset } = useRoomState()
  const now = useNow() + clockOffset
  const playing = view.phase === 'playing'
  const remaining = useRemainingMs(playing ? view.runEndsAt : null)
  const seconds = remaining === null ? 0 : Math.ceil(remaining / 1000)
  const flash = view.lastResult?.correct && now - view.puzzleStartedAt < FLASH_MS ? view.lastResult.points : null
  const skipSeconds = C.SOLO_GUESS_SKIP_PENALTY_MS / 1000

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    const guess = text.trim()
    if (!guess || !playing || sending) return
    setSending(true)
    await send({ type: 'guess', text: guess })
    setSending(false)
    setText('')
    input.current?.focus()
  }

  const skip = async () => {
    if (!playing || sending) return
    setSending(true)
    await send({ type: 'skip' })
    setSending(false)
    input.current?.focus()
  }

  return (
    <div className="stack guess solo-run">
      <div className="solo-run__stats">
        <span>Score {view.score}</span>
        <span>Solved {view.solved}</span>
        <span>Level {view.level}</span>
      </div>
      {playing && (
        <>
          <p className={`solo-run__clock${seconds <= 3 ? ' solo-run__clock--low' : ''}`} role="timer" aria-label={`${seconds} seconds left`}>
            {seconds}
          </p>
          <TimerBar deadline={view.runEndsAt} totalMs={C.SOLO_GUESS_RUN_MS} label="Run time left" />
        </>
      )}

      {playing && view.prompt && (
        <div
          className="guess__prompt"
          aria-label={view.kind === 'scramble' ? `Scrambled letters: ${view.prompt.split('').join(' ')}` : `Emojis: ${view.prompt}`}
        >
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
      )}

      <div aria-live="polite">
        {flash !== null && <p className="solo-run__flash">+{flash}</p>}
        {view.lastResult?.answerIfSkipped && <p className="muted solo-run__reveal">It was {view.lastResult.answerIfSkipped}</p>}
      </div>

      {playing && view.hints.length > 0 && (
        <ul className="guess__hints" aria-label="Hints">
          {view.hints.map((h) => (
            <li key={h.type} className="guess__hint">
              💡 {hintText(h)}
            </li>
          ))}
        </ul>
      )}

      {playing && (
        <>
          <form className="guess__form" onSubmit={submit}>
            <label htmlFor="guess-run-input" className="visually-hidden">
              Your answer
            </label>
            <input
              id="guess-run-input"
              ref={input}
              className="field__input"
              value={text}
              onChange={(e) => setText(e.target.value)}
              maxLength={C.GUESS_TEXT_MAX}
              placeholder="Type your answer"
              autoComplete="off"
              autoCorrect="off"
              autoCapitalize="off"
              spellCheck={false}
              enterKeyHint="send"
              autoFocus
            />
            <Button type="submit" disabled={!text.trim() || sending}>
              Send
            </Button>
          </form>
          <Button variant="secondary" block onClick={() => void skip()} disabled={sending}>
            Skip (-{skipSeconds}s)
          </Button>
        </>
      )}
    </div>
  )
}
