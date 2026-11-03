import { useRef, useState, type FormEvent } from 'react'
import { Button } from '../../../components/Button'
import { CountdownRing } from '../../../components/CountdownRing'
import { C } from '../../../lib/constants'
import type { NameItRunView } from '../../../types/views'
import type { GameAction } from '../../types'
import { Strikes } from '../Strikes'
import '../solo.css'

const FEEDBACK: Record<string, string> = {
  correct: '✓ Correct!',
  wrong: 'Not on our list',
  repeat: 'Already said',
  timeout: "Time's up",
}

/** Name It "Streak" (PROTOCOL.md 16.1). Only answers already given are ever on screen. */
export function NameItRun({ view, send }: { view: NameItRunView; send: (action: GameAction) => Promise<boolean> }) {
  const [text, setText] = useState('')
  const [sending, setSending] = useState(false)
  const input = useRef<HTMLInputElement>(null)
  const playing = view.phase === 'playing'

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    const answer = text.trim()
    if (!answer || !playing || sending) return
    setSending(true)
    await send({ type: 'submitAnswer', text: answer })
    setSending(false)
    setText('')
    input.current?.focus()
  }

  return (
    <div className="stack solo-run">
      <h2 className="solo-run__topic">
        <span aria-hidden="true">{view.topic.emoji} </span>
        {view.topic.name}
      </h2>
      <div className="solo-run__row">
        <p className="solo-run__big" aria-label={`Streak ${view.streak}`}>
          {view.streak}
        </p>
        {playing && <CountdownRing deadline={view.turnEndsAt} totalMs={C.NAMEIT_TURN_MS} />}
      </div>
      <Strikes strikes={view.strikes} max={view.maxStrikes} />
      <p className="solo-run__feedback" aria-live="polite">
        {view.lastResult ? FEEDBACK[view.lastResult.kind] : ''}
      </p>
      {playing && (
        <form className="guess__form" onSubmit={submit}>
          <label htmlFor="name-it-input" className="visually-hidden">
            Your answer
          </label>
          <input
            id="name-it-input"
            ref={input}
            className="field__input"
            value={text}
            onChange={(e) => setText(e.target.value)}
            maxLength={40}
            placeholder={`Name ${view.topic.name.toLowerCase()}`}
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
      )}
      {view.accepted.length > 0 && (
        <ul className="solo-run__answers" aria-label="Your answers, newest first">
          {view.accepted.map((name) => (
            <li key={name}>{name}</li>
          ))}
        </ul>
      )}
    </div>
  )
}
