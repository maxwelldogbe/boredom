import { useState, type FormEvent } from 'react'
import { Button } from '../../components/Button'
import { CountdownRing } from '../../components/CountdownRing'
import { PlayerChip } from '../../components/PlayerChip'
import { TextInput } from '../../components/TextInput'
import { TimerBar } from '../../components/TimerBar'
import { C } from '../../lib/constants'
import { formatPoints } from '../../lib/format'
import { nameOf, playerById } from '../../lib/players'
import { useRemainingMs } from '../../state/useCountdown'
import type { HangmanView } from '../../types/views'
import { ScoresStrip } from '../ScoresStrip'
import type { GameUiProps } from '../types'
import { Gallows } from './Gallows'
import './hangman.css'

// Alphabetical 6-column grid keeps every key ≥44px wide even on a 320px screen.
const ALPHABET = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'.split('')
const WORD_MIN = C.HANGMAN_WORD_MIN
const WORD_MAX = C.HANGMAN_WORD_MAX

/** Hangman Duel (plan section 9). The secret word is only in the setter's view. */
export function HangmanGame({ view, send, me, room }: GameUiProps<HangmanView>) {
  const setterName = nameOf(room, view.setterId, me)
  return (
    <div className="stack hangman">
      <div className="hangman__header">
        <span>
          Round {view.round}/{view.total}
        </span>
        <PlayerChip player={playerById(room, view.setterId)} isMe={view.setterId === me} size="sm" extra="sets the word" />
      </div>

      {view.phase === 'setting' ? (
        view.isSetter ? (
          <SetWordForm view={view} send={send} />
        ) : (
          <div className="hangman__waiting" role="status">
            <CountdownRing deadline={view.deadline} totalMs={C.HANGMAN_SET_WORD_MS} />
            <p>⏳ Waiting for {setterName} to choose a word…</p>
          </div>
        )
      ) : (
        <Board view={view} send={send} setterName={setterName} room={room} me={me} />
      )}

      <ScoresStrip scores={view.scores} room={room} me={me} />
    </div>
  )
}

function SetWordForm({ view, send }: Pick<GameUiProps<HangmanView>, 'view' | 'send'>) {
  const [word, setWord] = useState('')
  const [hint, setHint] = useState('')
  const [sending, setSending] = useState(false)
  const ok = word.length >= WORD_MIN && word.length <= WORD_MAX

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (!ok) return
    setSending(true)
    const sent = await send({ type: 'setWord', word, ...(hint.trim() ? { hint: hint.trim() } : {}) })
    if (!sent) setSending(false)
  }

  return (
    <form className="stack" onSubmit={submit} noValidate>
      <div className="hangman__waiting">
        <CountdownRing deadline={view.deadline} totalMs={C.HANGMAN_SET_WORD_MS} />
        <p>Your turn to pick a secret word!</p>
      </div>
      <TextInput
        label="Secret word"
        value={word}
        onChange={(e) => setWord(e.target.value.replace(/[^a-z]/gi, '').toUpperCase())}
        maxLength={WORD_MAX}
        autoComplete="off"
        autoCapitalize="characters"
        spellCheck={false}
        hint={`${WORD_MIN} to ${WORD_MAX} letters, A–Z only`}
      />
      <TextInput
        label="Hint (optional)"
        value={hint}
        onChange={(e) => setHint(e.target.value)}
        maxLength={C.HANGMAN_HINT_MAX}
        autoComplete="off"
        hint="For example: an animal"
      />
      <Button type="submit" block disabled={!ok || sending}>
        {sending ? 'Saving…' : 'Use this word'}
      </Button>
    </form>
  )
}

function Board({ view, send, setterName, room, me }: GameUiProps<HangmanView> & { setterName: string }) {
  const [pending, setPending] = useState<string | null>(null)
  const canGuess = view.phase === 'guessing' && !view.isSetter
  const letters = view.word ? view.word.split('') : view.mask.map((m) => m ?? '')

  const guess = async (letter: string) => {
    setPending(letter)
    await send({ type: 'guessLetter', letter })
    setPending(null)
  }

  return (
    <>
      <div className="hangman__board">
        <Gallows wrongCount={view.wrongCount} maxWrong={view.maxWrong} />
        <p className="hangman__wrong">
          Wrong: {view.wrongCount}/{view.maxWrong}
          {view.wrong.length > 0 && ` (${view.wrong.join(', ')})`}
        </p>
      </div>

      <div className="hangman__word" aria-label={`Word: ${view.mask.map((m) => m ?? 'blank').join(' ')}`}>
        {view.mask.map((cell, i) => (
          <span key={i} className={`hangman__cell${cell ? '' : ' hangman__cell--hidden'}`} aria-hidden="true">
            {cell ?? (view.isSetter || view.phase !== 'guessing' ? letters[i] : '')}
          </span>
        ))}
      </div>
      {view.hint && <p className="hangman__hint">💡 {view.hint}</p>}

      {view.phase === 'guessing' && view.isSetter && (
        <p className="notice" role="status">
          Guessers are guessing… You can't guess your own word.
        </p>
      )}

      {canGuess && (
        <div className="keyboard" aria-label="Letters">
          {ALPHABET.map((letter) => {
            const isWrong = view.wrong.includes(letter)
            const isRight = !isWrong && view.guessed.includes(letter)
            return (
              <button
                key={letter}
                type="button"
                className={`keyboard__key${isWrong ? ' keyboard__key--wrong' : ''}${isRight ? ' keyboard__key--right' : ''}`}
                disabled={isWrong || isRight || pending !== null}
                onClick={() => guess(letter)}
                aria-label={`${letter}${isWrong ? ', wrong' : isRight ? ', correct' : ''}`}
              >
                {letter}
                {isWrong && <span aria-hidden="true">✕</span>}
                {isRight && <span aria-hidden="true">✓</span>}
              </button>
            )
          })}
        </div>
      )}

      {view.phase === 'guessing' && (
        <p className="muted hangman__pot">
          Round pot: {view.pot} points. Each wrong letter moves {view.wrongCost} to the setter.
        </p>
      )}

      {(view.phase === 'roundOver' || view.phase === 'flagVote' || view.phase === 'done') && (
        <p className="hangman__result" role="status">
          {view.result === 'guessers' && `🎉 Solved! The word was ${view.word}.`}
          {view.result === 'setter' && `🪢 ${setterName === 'You' ? 'You win' : `${setterName} wins`} this round! The word was ${view.word}.`}
          {view.result === 'skipped' && `⌛ ${setterName === 'You' ? "You didn't" : `${setterName} didn't`} pick a word in time. Round skipped.`}
        </p>
      )}
      {view.phase !== 'guessing' && Object.keys(view.award).length > 0 && <Award view={view} room={room} me={me} />}
      {view.phase === 'roundOver' && <FlagButton view={view} send={send} />}
      {view.phase === 'flagVote' && view.flag && <FlagVote view={view} send={send} room={room} me={me} />}
      {view.phase === 'roundOver' && <p className="muted">Next round starting…</p>}
      {view.phase === 'done' && (
        <p className="muted">That was the last round. Results coming up…</p>
      )}
    </>
  )
}

function Award({ view, room, me }: Pick<GameUiProps<HangmanView>, 'view' | 'room' | 'me'>) {
  const parts = Object.entries(view.award).map(([pid, pts]) => `${nameOf(room, pid, me)} +${formatPoints(pts)}`)
  return <p className="hangman__award">This round: {parts.join(' · ')}</p>
}

function FlagButton({ view, send }: Pick<GameUiProps<HangmanView>, 'view' | 'send'>) {
  const left = useRemainingMs(view.flagUntil)
  const [sending, setSending] = useState(false)
  if (!view.canFlag || !view.flagUntil || !left) return null
  const flag = async () => {
    setSending(true)
    await send({ type: 'flagWord' })
    setSending(false)
  }
  return (
    <section className="stack" aria-label="Flag the word">
      <Button variant="secondary" block disabled={sending} onClick={flag}>
        🚩 Not a real word?
      </Button>
      <TimerBar deadline={view.flagUntil} totalMs={C.HANGMAN_FLAG_WINDOW_MS} label="Flag window" />
    </section>
  )
}

function FlagVote({ view, send, room, me }: GameUiProps<HangmanView>) {
  const flag = view.flag!
  const [sending, setSending] = useState(false)
  const vote = async (valid: boolean) => {
    setSending(true)
    if (!(await send({ type: 'voteWord', valid }))) setSending(false)
  }
  return (
    <section className="stack hangman__vote" aria-label="Vote on the word">
      <p>
        🚩 <strong>{nameOf(room, flag.flaggerId, me)}</strong> says <strong>{view.word}</strong> is not a real word.
      </p>
      <TimerBar deadline={flag.deadline} totalMs={C.HANGMAN_VOTE_MS} label="Vote closes" />
      {flag.canVote ? (
        <div className="hangman__vote-buttons">
          <Button variant="secondary" disabled={sending} onClick={() => vote(true)}>
            ✓ It's a word
          </Button>
          <Button variant="danger" disabled={sending} onClick={() => vote(false)}>
            ✗ Not a word
          </Button>
        </div>
      ) : (
        <p className="muted">
          {flag.hasVoted ? 'Vote cast. ' : ''}Votes in: {flag.votedCount}/{flag.voterIds.length}
        </p>
      )}
    </section>
  )
}
