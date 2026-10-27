import { useState, type ChangeEvent, type FormEvent } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { Button } from '../components/Button'
import { Modal } from '../components/Modal'
import { TextInput } from '../components/TextInput'
import {
  AccountError,
  adoptSession,
  deleteAccount,
  fetchMe,
  fetchMyStats,
  fetchRecentPlayers,
  forgetAccount,
  getAuthToken,
  updateAccountProfile,
} from '../lib/account'
import {
  exportProfile,
  getProfile,
  importProfile,
  resetProfile,
  saveProfile,
  type Profile,
} from '../lib/profileStore'
import { friendlyError } from '../lib/errors'
import { resetPopupDismissals } from '../lib/guestPopup'
import { safeNext } from '../lib/navigation'
import { useRoomActions } from '../state/context'
import type { Avatar } from '../types/protocol'
import { AccountForms } from './AccountForms'
import { ProfileForm } from './ProfileForm'
import {
  ByGameSection,
  ProfileHeader,
  RecentPlayersSection,
  StatsSection,
  type HeaderData,
} from './profile/ProfileSections'
import { useLoad } from './profile/useLoad'
import { WhatWeSave } from './profile/WhatWeSave'

const LOGIN_EXPIRED = 'Your login has expired. Log in again to use your saved profile.'

function currentProfile(): Profile | null {
  const profile = getProfile()
  // A registered profile without a token (cleared storage) is a guest again.
  if (profile?.type === 'registered' && !getAuthToken()) return forgetAccount()
  return profile
}

/** Edit the profile; guests can save it as an account, registered players manage theirs. */
export default function ProfilePage() {
  const [profile, setProfile] = useState<Profile | null>(currentProfile)
  if (!profile) return null // RequireProfile guards this route
  return profile.type === 'registered' ? (
    <AccountProfilePage profile={profile} onChange={setProfile} />
  ) : (
    <GuestProfilePage profile={profile} onChange={setProfile} />
  )
}

interface PageProps {
  profile: Profile
  onChange: (profile: Profile) => void
}

function GuestProfilePage({ profile, onChange }: PageProps) {
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const { toast, joinRoom } = useRoomActions()
  const [formKey, setFormKey] = useState(0)
  const [importError, setImportError] = useState<string | null>(null)
  const [confirmReset, setConfirmReset] = useState(false)

  const onImport = async (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    const result = importProfile(await file.text(), profile.id)
    if (!result.ok) {
      setImportError(result.error)
      return
    }
    const guest: Profile = { ...result.profile, type: 'guest' }
    delete guest.username
    saveProfile(guest)
    onChange(guest)
    setFormKey((k) => k + 1)
    setImportError(null)
    toast('Profile imported.')
  }

  /** Back to where the player was. A room is re-joined first with the stored roomToken and the
   *  new login, so the guest seat becomes the account's seat; if it is gone, go home. */
  const returnTo = async (next: string) => {
    const room = next.match(/^\/room\/([A-Za-z]+)$/)
    if (room) {
      try {
        await joinRoom(room[1])
      } catch (err) {
        toast(`We couldn't take you back to room ${room[1].toUpperCase()}. ${friendlyError(err, room[1].toUpperCase())}`, 'error')
        navigate('/', { replace: true })
        return
      }
    }
    navigate(next, { replace: true })
  }

  return (
    <main className="page stack">
      <Link to="/" className="back-link">
        ← Home
      </Link>
      <h1>Your profile</h1>
      <ProfileForm
        key={formKey}
        initial={profile}
        submitLabel="Save changes"
        onSubmit={(fields) => {
          const updated = { ...profile, ...fields }
          saveProfile(updated)
          onChange(updated)
          toast('Profile saved.')
        }}
      />
      <section className="card stack" aria-labelledby="account-heading">
        <h2 id="account-heading">Save your profile</h2>
        <p className="muted">
          Create a free account to keep your name, color and avatar on any device. You can keep
          playing as a guest without one.
        </p>
        <AccountForms
          allowSignup
          initialMode={params.get('mode') === 'login' ? 'login' : 'signup'}
          onSignedIn={(saved, mode) => {
            if (mode === 'signup') resetPopupDismissals()
            toast(mode === 'signup' ? 'Account created. Your profile is saved.' : `Welcome back, ${saved.nickname}!`)
            const next = params.get('next')
            if (!next) return onChange(saved)
            void returnTo(safeNext(next))
          }}
        />
      </section>
      <WhatWeSave registered={false} />
      <section className="stack">
        <h2>Backup</h2>
        <Button variant="secondary" block onClick={() => exportProfile(profile)}>
          Export profile
        </Button>
        <label className="btn btn--secondary btn--block">
          Import profile
          <input type="file" accept="application/json,.json" className="visually-hidden" onChange={onImport} />
        </label>
        {importError && (
          <p className="field__error" role="alert">
            {importError}
          </p>
        )}
      </section>
      <Button variant="danger" block onClick={() => setConfirmReset(true)}>
        Reset profile
      </Button>
      {confirmReset && (
        <Modal
          title="Reset your profile?"
          onClose={() => setConfirmReset(false)}
          actions={
            <>
              <Button
                variant="danger"
                block
                onClick={() => {
                  resetProfile()
                  navigate('/setup', { replace: true })
                }}
              >
                Reset
              </Button>
              <Button variant="secondary" block onClick={() => setConfirmReset(false)}>
                Cancel
              </Button>
            </>
          }
        >
          <p>Your nickname, avatar and stats on this device will be deleted.</p>
        </Modal>
      )}
    </main>
  )
}

function AccountProfilePage({ profile, onChange }: PageProps) {
  const { toast } = useRoomActions()
  const [saving, setSaving] = useState(false)
  const [formKey, setFormKey] = useState(0)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [avatarLockedUntil, setAvatarLockedUntil] = useState<number | null>(null)

  const expired = () => {
    const guest = forgetAccount()
    if (guest) onChange(guest)
    toast(LOGIN_EXPIRED, 'error')
  }

  const token = () => {
    const value = getAuthToken()
    if (!value) throw new AccountError('UNAUTHORIZED', 'Please log in again.')
    return value
  }
  // The header refreshes the saved profile and stats from the server (and reads the tag);
  // stats and recent players load on their own, so one failing never hides the others.
  const [me, retryMe] = useLoad<HeaderData>(async () => {
    const data = await fetchMe(token())
    onChange(adoptSession(data))
    setAvatarLockedUntil(data.profile.avatarLockedUntil ?? null)
    setFormKey((k) => k + 1)
    return { tag: data.tag, createdAt: data.createdAt }
  }, expired)
  const [stats, retryStats] = useLoad(() => fetchMyStats(token()), expired)
  const [players, retryPlayers] = useLoad(() => fetchRecentPlayers(token()), expired)

  const save = async (fields: { nickname: string; color: string }, avatar?: Avatar) => {
    const token = getAuthToken()
    if (!token) return expired()
    setSaving(true)
    try {
      const saved = await updateAccountProfile(token, avatar ? { ...fields, avatar } : fields)
      onChange(adoptSession({ profile: saved, stats: profile.stats }))
      setAvatarLockedUntil(saved.avatarLockedUntil ?? null)
      toast(avatar ? 'Profile saved. Enjoy your new avatar!' : 'Profile saved.')
    } catch (err) {
      if (err instanceof AccountError && err.code === 'UNAUTHORIZED') expired()
      else if (err instanceof AccountError && err.code === 'AVATAR_LOCKED') {
        // Changed on another device: show the real lock (this also resets the form).
        toast(err.fields.avatar ?? err.message, 'error')
        retryMe()
      } else toast(err instanceof AccountError ? (Object.values(err.fields)[0] ?? err.message) : 'Could not save.', 'error')
    } finally {
      setSaving(false)
    }
  }

  return (
    <main className="page stack">
      <Link to="/" className="back-link">
        ← Home
      </Link>
      <ProfileHeader nickname={profile.nickname} color={profile.color} avatar={profile.avatar} me={me} onRetry={retryMe} />
      <StatsSection stats={stats} onRetry={retryStats} />
      <ByGameSection stats={stats} onRetry={retryStats} />
      <RecentPlayersSection players={players} onRetry={retryPlayers} />
      <ProfileForm
        key={formKey}
        initial={profile}
        savedAvatar={profile.avatar}
        avatarLockedUntil={avatarLockedUntil}
        submitLabel="Save changes"
        busy={saving}
        onSubmit={save}
      />
      <WhatWeSave registered />
      <section className="stack">
        <h2>Account</h2>
        <Button
          variant="secondary"
          block
          onClick={() => {
            const guest = forgetAccount()
            if (guest) onChange(guest)
            toast("Logged out. You're playing as a guest on this device.")
          }}
        >
          Log out
        </Button>
        <Button variant="danger" block onClick={() => setConfirmDelete(true)}>
          Delete account
        </Button>
      </section>
      {confirmDelete && (
        <DeleteAccountModal
          onClose={() => setConfirmDelete(false)}
          onDeleted={() => {
            const guest = forgetAccount()
            if (guest) onChange(guest)
            toast('Your account was deleted.')
          }}
          onExpired={expired}
        />
      )}
    </main>
  )
}

function DeleteAccountModal({
  onClose,
  onDeleted,
  onExpired,
}: {
  onClose: () => void
  onDeleted: () => void
  onExpired: () => void
}) {
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const submit = async (e?: FormEvent) => {
    e?.preventDefault()
    const token = getAuthToken()
    if (!token) return onExpired()
    if (!password) return setError('Enter your password.')
    setBusy(true)
    try {
      await deleteAccount(token, password)
      onDeleted()
    } catch (err) {
      setBusy(false)
      if (err instanceof AccountError && err.code === 'UNAUTHORIZED') return onExpired()
      setError(
        err instanceof AccountError && err.code === 'INVALID_CREDENTIALS'
          ? 'Wrong password.'
          : err instanceof AccountError
            ? err.message
            : 'Could not delete the account.',
      )
    }
  }

  return (
    <Modal
      title="Delete your account?"
      onClose={onClose}
      actions={
        <>
          <Button variant="danger" block disabled={busy} onClick={() => void submit()}>
            {busy ? 'Deleting…' : 'Delete account'}
          </Button>
          <Button variant="secondary" block onClick={onClose} disabled={busy}>
            Cancel
          </Button>
        </>
      }
    >
      <form className="stack" onSubmit={submit} noValidate>
        <p>
          Your login, saved profile and stats are deleted for good. Games you played are kept only as
          anonymous totals. You can keep playing as a guest.
        </p>
        <TextInput
          label="Password"
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(e) => {
            setPassword(e.target.value)
            setError(null)
          }}
          error={error}
        />
      </form>
    </Modal>
  )
}
