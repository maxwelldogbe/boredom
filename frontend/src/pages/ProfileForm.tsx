import { useState, type FormEvent } from 'react'
import { Button } from '../components/Button'
import { PlayerChip } from '../components/PlayerChip'
import { TextInput } from '../components/TextInput'
import { C } from '../lib/constants'
import { nicknameError, type ProfileFields } from '../lib/profileStore'
import type { Avatar } from '../types/protocol'

interface ProfileFormProps {
  initial?: ProfileFields
  submitLabel: string
  onSubmit: (fields: ProfileFields) => void
  /** A registered account's saved avatar (guests get a random one per room). */
  savedAvatar?: Avatar
  busy?: boolean
}

/** Nickname, color swatches and a live preview chip. */
export function ProfileForm({ initial, submitLabel, onSubmit, savedAvatar, busy = false }: ProfileFormProps) {
  const [nickname, setNickname] = useState(initial?.nickname ?? '')
  const [color, setColor] = useState(initial?.color ?? C.PLAYER_COLORS[0])
  const [touched, setTouched] = useState(false)
  const error = nicknameError(nickname)

  const submit = (e: FormEvent) => {
    e.preventDefault()
    setTouched(true)
    if (!error) onSubmit({ nickname: nickname.trim(), color })
  }

  return (
    <form className="stack" onSubmit={submit} noValidate>
      <div className="profile-preview" aria-live="polite">
        <PlayerChip
          player={{ nickname: nickname.trim() || 'Your name', color, avatar: savedAvatar, type: savedAvatar ? 'registered' : undefined }}
        />
      </div>
      <p className="muted">
        {savedAvatar
          ? 'Your avatar is saved with your account and follows you into every room.'
          : 'You get a random avatar each time you join a room.'}
      </p>
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
      <Button type="submit" block disabled={Boolean(error) || busy}>
        {busy ? 'Saving…' : submitLabel}
      </Button>
    </form>
  )
}
