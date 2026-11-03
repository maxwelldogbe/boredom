import { useState } from 'react'
import type { HangmanRunView } from '../../../types/views'
import { Gallows } from '../../hangman/Gallows'
import type { GameAction } from '../../types'
import { Strikes } from '../Strikes'
import '../../hangman/hangman.css'
import '../solo.css'

const ALPHABET = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'.split('')

/** Hangman "Word streak" (PROTOCOL.md 16.1). The word only arrives once it is lost. */
export function HangmanRun({ view, send }: { view: HangmanRunView; send: (action: GameAction) => Promise<boolean> }) {
  const [pending, setPending] = useState<string | null>(null)
  const guessing = view.phase === 'guessing'
  const wrong = view.guessed.wrong.map((l) => l.toUpperCase())
  const right = view.guessed.correct.map((l) => l.toUpperCase())
  const revealed = view.revealedWord ? view.revealedWord.toUpperCase().split('') : null

  const guess = async (letter: string) => {
    setPending(letter)
    await send({ type: 'guessLetter', letter })
    setPending(null)
  }

  return (
    <div className="stack hangman solo-run">
      <div className="solo-run__stats">
        <span>Words solved {view.solved}</span>
        <span>Word {view.wordNumber}</span>
        <span>Level {view.level}</span>
      </div>
      <Strikes strikes={view.strikes} max={view.maxStrikes} />
      <div className="hangman__board">
        <Gallows wrongCount={view.wrongCount} maxWrong={view.maxWrong} />
        <p className="hangman__wrong">
          Wrong: {view.wrongCount}/{view.maxWrong}
        </p>
      </div>
      <div className="hangman__word" aria-label={`Word: ${view.mask.map((m) => m?.toUpperCase() ?? 'blank').join(' ')}`}>
        {view.mask.map((cell, i) => (
          <span key={i} className={`hangman__cell${cell ? '' : ' hangman__cell--hidden'}`} aria-hidden="true">
            {cell?.toUpperCase() ?? revealed?.[i] ?? ''}
          </span>
        ))}
      </div>
      <p className="hangman__result" aria-live="polite">
        {revealed ? `The word was ${view.revealedWord!.toUpperCase()}.` : ''}
      </p>
      {guessing && (
        <div className="keyboard" aria-label="Letters">
          {ALPHABET.map((letter) => {
            const isWrong = wrong.includes(letter)
            const isRight = !isWrong && right.includes(letter)
            return (
              <button
                key={letter}
                type="button"
                className={`keyboard__key${isWrong ? ' keyboard__key--wrong' : ''}${isRight ? ' keyboard__key--right' : ''}`}
                disabled={isWrong || isRight || pending !== null}
                onClick={() => void guess(letter)}
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
    </div>
  )
}
