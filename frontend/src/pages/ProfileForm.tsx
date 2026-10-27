import { useState, type FormEvent } from 'react'
import { Button } from '../components/Button'
import { PlayerChip } from '../components/PlayerChip'
import { TextInput } from '../components/TextInput'
import { randomAvatar } from '../lib/avatar'
import { C } from '../lib/constants'
import { longDate } from '../lib/format'
import { nicknameError, type ProfileFields } from '../lib/profileStore'
import type { Avatar } from '../types/protocol'
import { RingAvatar } from './profile/ProfileSections'

interface ProfileFormProps {
  initial?: ProfileFields
  submitLabel: string
  /** `avatar` is set only when a registered player picked a new one. */
  onSubmit: (fields: ProfileFields, avatar?: Avatar) => void
  /** A registered account's saved avatar (guests get a random one per room). */
  savedAvatar?: Avatar
  /** Epoch ms until which the saved avatar can't be changed; null or missing means now. */
  avatarLockedUntil?: number | null
  busy?: boolean
}

/** Nickname, color swatches, an avatar shuffle for accounts and a live preview chip. */
export function ProfileForm({
  initial,
  submitLabel,
  onSubmit,
  savedAvatar,
  avatarLockedUntil = null,
  busy = false,
}: ProfileFormProps) {
  const [nickname, setNickname] = useState(initial?.nickname ?? '')
  const [color, setColor] = useState(initial?.color ?? C.PLAYER_COLORS[0])
  const [picked, setPicked] = useState<Avatar | null>(null)
  const [touched, setTouched] = useState(false)
  const error = nicknameError(nickname)
  const [openedAt] = useState(() => Date.now())
  const unlockAt = avatarLockedUntil !== null && avatarLockedUntil > openedAt ? avatarLockedUntil : null
  const locked = unlockAt !== null
  // A shuffled avatar only counts while it differs from the saved one and a change is allowed.
  const newAvatar =
    !locked && picked && (picked.style !== savedAvatar?.style || picked.seed !== savedAvatar?.seed) ? picked : null
  const avatar = newAvatar ?? savedAvatar

  const submit = (e: FormEvent) => {
    e.preventDefault()
    setTouched(true)
    if (!error) onSubmit({ nickname: nickname.trim(), color }, newAvatar ?? undefined)
  }

  return (
    <form className="stack" onSubmit={submit} noValidate>
      <div className="profile-preview" aria-live="polite">
        <PlayerChip
          player={{ nickname: nickname.trim() || 'Your name', color, avatar, type: savedAvatar ? 'registered' : undefined }}
        />
      </div>
      {savedAvatar ? (
        <fieldset className="picker avatar-picker">
          <legend className="field__label">Avatar</legend>
          <div className="avatar-picker__row">
            <RingAvatar avatar={avatar} nickname={nickname.trim() || 'Your name'} color={color} size={80} />
            <div className="avatar-picker__actions">
              {!locked && (
                <Button variant="secondary" onClick={() => setPicked(randomAvatar(avatar))}>
                  Shuffle avatar
                </Button>
              )}
              {newAvatar && (
                <Button variant="ghost" onClick={() => setPicked(null)}>
                  Keep my current one
                </Button>
              )}
            </div>
          </div>
          <p className="muted avatar-picker__hint" aria-live="polite">
            {unlockAt !== null
              ? `You can change your avatar again on ${longDate(unlockAt)}.`
              : newAvatar
                ? `Save changes to keep this avatar. You can't change it again for ${C.AVATAR_CHANGE_DAYS} days.`
                : `Shuffle until you find one you like. You can change it once every ${C.AVATAR_CHANGE_DAYS} days.`}
          </p>
        </fieldset>
      ) : (
        <p className="muted">You get a random avatar each time you join a room.</p>
      )}
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
