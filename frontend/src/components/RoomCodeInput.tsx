import { useRef, type ClipboardEvent, type KeyboardEvent } from 'react'
import { C } from '../lib/constants'
import { cleanCodeInput } from '../lib/roomCode'

interface RoomCodeInputProps {
  value: string
  onChange: (value: string) => void
  onComplete?: (value: string) => void
  disabled?: boolean
  invalid?: boolean
}

/** One box per letter: auto-uppercase, auto-advance, backspace goes back, paste fills all. */
export function RoomCodeInput({ value, onChange, onComplete, disabled, invalid }: RoomCodeInputProps) {
  const boxes = useRef<(HTMLInputElement | null)[]>([])
  const length = C.ROOM_CODE_LENGTH
  const letters = Array.from({ length }, (_, i) => value[i] ?? '')

  const update = (next: string, focusIndex: number) => {
    const clipped = next.slice(0, length)
    onChange(clipped)
    boxes.current[Math.min(focusIndex, length - 1)]?.focus()
    if (clipped.length === length) onComplete?.(clipped)
  }

  const handleInput = (index: number, raw: string) => {
    const typed = cleanCodeInput(raw)
    if (!typed) return
    const next = (value.slice(0, index) + typed + value.slice(index + typed.length)).slice(0, length)
    update(next, index + typed.length)
  }

  const handleKeyDown = (index: number, e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Backspace') {
      e.preventDefault()
      if (letters[index]) update(value.slice(0, index) + value.slice(index + 1), index)
      else if (index > 0) update(value.slice(0, index - 1) + value.slice(index), index - 1)
    } else if (e.key === 'ArrowLeft' && index > 0) {
      boxes.current[index - 1]?.focus()
    } else if (e.key === 'ArrowRight' && index < length - 1) {
      boxes.current[index + 1]?.focus()
    }
  }

  const handlePaste = (e: ClipboardEvent<HTMLInputElement>) => {
    e.preventDefault()
    const pasted = cleanCodeInput(e.clipboardData.getData('text'))
    if (pasted) update(pasted, pasted.length)
  }

  return (
    <div className="code-input" role="group" aria-label="Room code">
      {letters.map((letter, i) => (
        <input
          key={i}
          ref={(el) => {
            boxes.current[i] = el
          }}
          className="code-input__box"
          value={letter}
          onChange={(e) => handleInput(i, e.target.value.replace(letter, '') || e.target.value)}
          onKeyDown={(e) => handleKeyDown(i, e)}
          onPaste={handlePaste}
          onFocus={(e) => e.target.select()}
          inputMode="text"
          autoCapitalize="characters"
          autoComplete="off"
          autoCorrect="off"
          spellCheck={false}
          maxLength={length}
          disabled={disabled}
          aria-label={`Room code letter ${i + 1}`}
          aria-invalid={invalid ? true : undefined}
        />
      ))}
    </div>
  )
}
