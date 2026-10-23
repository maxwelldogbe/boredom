import { useEffect, useState, type ChangeEvent, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Button } from '../components/Button'
import { Modal } from '../components/Modal'
import { PlayerChip } from '../components/PlayerChip'
import { TextInput } from '../components/TextInput'
import { GAME_UIS } from '../games/registry'
import {
  AccountError,
  adoptSession,
  deleteAccount,
  fetchMe,
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
import { useRoomActions } from '../state/context'
import type { GameId } from '../types/protocol'
import { AccountForms } from './AccountForms'
import { ProfileForm } from './ProfileForm'

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
  const { toast } = useRoomActions()
  const [formKey, setFormKey] = useState(0)
  const [importError, setImportError] = useState<string | null>(null)
  const [confirmReset, setConfirmReset] = useState(false)

  const onImport = async (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    const result = importProfile(await file.text())
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
          onSignedIn={(saved, mode) => {
            onChange(saved)
            toast(mode === 'signup' ? 'Account created. Your profile is saved.' : `Welcome back, ${saved.nickname}!`)
          }}
        />
      </section>
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

  const expired = () => {
    const guest = forgetAccount()
    if (guest) onChange(guest)
    toast(LOGIN_EXPIRED, 'error')
  }

  // Refresh the saved profile and stats from the server.
  useEffect(() => {
    const token = getAuthToken()
    if (!token) return
    let live = true
    fetchMe(token)
      .then((me) => {
        if (!live) return
        onChange(adoptSession(me))
        setFormKey((k) => k + 1)
      })
      .catch((err: unknown) => {
        if (live && err instanceof AccountError && err.code === 'UNAUTHORIZED') expired()
      })
    return () => {
      live = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- once per visit
  }, [])

  const save = async (fields: { nickname: string; color: string }) => {
    const token = getAuthToken()
    if (!token) return expired()
    setSaving(true)
    try {
      const saved = await updateAccountProfile(token, fields)
      onChange(adoptSession({ profile: saved, stats: profile.stats }))
      toast('Profile saved.')
    } catch (err) {
      if (err instanceof AccountError && err.code === 'UNAUTHORIZED') expired()
      else toast(err instanceof AccountError ? (Object.values(err.fields)[0] ?? err.message) : 'Could not save.', 'error')
    } finally {
      setSaving(false)
    }
  }

  const byGame = Object.entries(profile.stats.byGame).filter(([, s]) => s.played > 0)

  return (
    <main className="page stack">
      <Link to="/" className="back-link">
        ← Home
      </Link>
      <h1>Your profile</h1>
      <p className="account__who">
        <PlayerChip player={{ ...profile, type: 'registered' }} />
        <span className="muted">Logged in as @{profile.username}</span>
      </p>
      <ProfileForm
        key={formKey}
        initial={profile}
        savedAvatar={profile.avatar}
        submitLabel="Save changes"
        busy={saving}
        onSubmit={save}
      />
      <section className="stack" aria-labelledby="stats-heading">
        <h2 id="stats-heading">Your stats</h2>
        <p>
          {profile.stats.gamesPlayed} game{profile.stats.gamesPlayed === 1 ? '' : 's'} played,{' '}
          {profile.stats.wins} win{profile.stats.wins === 1 ? '' : 's'}.
        </p>
        {byGame.length > 0 && (
          <ul className="account__stats">
            {byGame.map(([id, s]) => (
              <li key={id}>
                <span>{GAME_UIS[id as GameId]?.name ?? id}</span>
                <span className="muted">
                  {s.wins} / {s.played} won
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>
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
