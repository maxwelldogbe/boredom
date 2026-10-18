import { useState, type FormEvent } from 'react'
import { Button } from '../components/Button'
import { PlayerChip } from '../components/PlayerChip'
import { TextInput } from '../components/TextInput'
import { C } from '../lib/constants'
import { nicknameError, type ProfileFields } from '../lib/profileStore'

interface ProfileFormProps {
  initial?: ProfileFields
  submitLabel: string
  onSubmit: (fields: ProfileFields) => void
}

/** Nickname, emoji grid, color swatches and a live preview chip. */
export function ProfileForm({ initial, submitLabel, onSubmit }: ProfileFormProps) {
  const [nickname, setNickname] = useState(initial?.nickname ?? '')
  const [emoji, setEmoji] = useState(initial?.emoji ?? C.EMOJI_PRESETS[0])
  const [color, setColor] = useState(initial?.color ?? C.PLAYER_COLORS[0])
  const [touched, setTouched] = useState(false)
  const error = nicknameError(nickname)

  const submit = (e: FormEvent) => {
    e.preventDefault()
    setTouched(true)
    if (!error) onSubmit({ nickname: nickname.trim(), emoji, color })
  }

  return (
    <form className="stack" onSubmit={submit} noValidate>
      <div className="profile-preview" aria-live="polite">
        <PlayerChip player={{ nickname: nickname.trim() || 'Your name', emoji, color }} />
      </div>
      <TextInput
        label="Nickname"
        value={nickname}
        maxLength={C.NICKNAME_MAX}
        autoComplete="nickname"
        onChange={(e) => setNickname(e.target.value)}
        onBlur={() => setTouched(true)}
        error={touched ? error : null}
        hint={`${C.NICKNAME_MIN} to ${C.NICKNAME_MAX} characters`}
      />
      <fieldset className="picker">
        <legend className="field__label">Emoji</legend>
        <div className="picker__grid picker__grid--emoji">
          {C.EMOJI_PRESETS.map((e) => (
            <button
              key={e}
              type="button"
              className="picker__item"
              aria-pressed={emoji === e}
              aria-label={`Emoji ${e}`}
              onClick={() => setEmoji(e)}
            >
              {e}
            </button>
          ))}
        </div>
      </fieldset>
      <fieldset className="picker">
        <legend className="field__label">Color</legend>
        <div className="picker__grid picker__grid--color">
          {C.PLAYER_COLORS.map((c, i) => (
            <button
              key={c}
              type="button"
              className="picker__item picker__swatch"
              style={{ background: c }}
              aria-pressed={color === c}
              aria-label={`Color ${i + 1}`}
              onClick={() => setColor(c)}
            >
              {color === c ? '✓' : ''}
            </button>
          ))}
        </div>
      </fieldset>
      <Button type="submit" block disabled={Boolean(error)}>
        {submitLabel}
      </Button>
    </form>
  )
}
