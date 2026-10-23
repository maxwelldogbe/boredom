import { useId, useState, type FormEvent } from 'react'
import { Button } from '../components/Button'
import { TextInput } from '../components/TextInput'
import {
  AccountError,
  adoptSession,
  login,
  passwordError,
  register,
  usernameError,
} from '../lib/account'
import { C } from '../lib/constants'
import { getProfile, type Profile } from '../lib/profileStore'

export type AccountMode = 'signup' | 'login'

function without(fields: Record<string, string>, name: string): Record<string, string> {
  const copy = { ...fields }
  delete copy[name]
  return copy
}

interface AccountFormsProps {
  /** Offer "Create account" (needs a guest profile on this device). */
  allowSignup: boolean
  initialMode?: AccountMode
  onSignedIn: (profile: Profile, mode: AccountMode) => void
}

/** Create an account from the guest profile, or log in to an existing one. */
export function AccountForms({ allowSignup, initialMode = 'signup', onSignedIn }: AccountFormsProps) {
  const [mode, setMode] = useState<AccountMode>(allowSignup ? initialMode : 'login')
  const tabsId = useId()
  return (
    <div className="stack">
      {allowSignup && (
        <div className="tabs" role="tablist" aria-label="Account">
          {(['signup', 'login'] as const).map((m) => (
            <button
              key={m}
              type="button"
              role="tab"
              id={`${tabsId}-${m}`}
              className="tabs__tab"
              aria-selected={mode === m}
              aria-controls={`${tabsId}-panel`}
              onClick={() => setMode(m)}
            >
              {m === 'signup' ? 'Create account' : 'Log in'}
            </button>
          ))}
        </div>
      )}
      <div id={`${tabsId}-panel`} role={allowSignup ? 'tabpanel' : undefined} aria-labelledby={allowSignup ? `${tabsId}-${mode}` : undefined}>
        <CredentialsForm key={mode} mode={mode} onSignedIn={onSignedIn} />
      </div>
    </div>
  )
}

function CredentialsForm({ mode, onSignedIn }: { mode: AccountMode; onSignedIn: AccountFormsProps['onSignedIn'] }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [touched, setTouched] = useState(false)
  const [busy, setBusy] = useState(false)
  const [serverFields, setServerFields] = useState<Record<string, string>>({})
  const [error, setError] = useState<string | null>(null)
  const signup = mode === 'signup'

  const localUsername = signup ? usernameError(username) : username ? null : 'Enter your username.'
  const localPassword = signup ? passwordError(password) : password ? null : 'Enter your password.'
  const usernameMsg = serverFields.username ?? (touched ? localUsername : null)
  const passwordMsg = serverFields.password ?? (touched ? localPassword : null)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setTouched(true)
    if (localUsername || localPassword || busy) return
    setBusy(true)
    setError(null)
    setServerFields({})
    try {
      let session
      if (signup) {
        const guest = getProfile()
        if (!guest) throw new AccountError('INVALID_INPUT', 'Set up your profile first.')
        session = await register(username, password, guest)
      } else {
        session = await login(username, password)
      }
      onSignedIn(adoptSession(session), mode)
    } catch (err) {
      setBusy(false)
      if (err instanceof AccountError) {
        const { username: u, password: p, ...other } = err.fields
        const fields: Record<string, string> = {}
        if (err.code === 'USERNAME_TAKEN') fields.username = err.message
        else if (u) fields.username = u
        if (p) fields.password = p
        setServerFields(fields)
        // Nickname or color problems (from the saved profile) and non-field errors go below.
        const general = Object.values(other)[0]
        setError(general ?? (Object.keys(fields).length ? null : err.message))
      } else {
        setError('Something went wrong. Please try again.')
      }
    }
  }

  return (
    <form className="stack" onSubmit={submit} noValidate>
      <TextInput
        label="Username"
        value={username}
        autoComplete="username"
        autoCapitalize="none"
        spellCheck={false}
        maxLength={20}
        onChange={(e) => {
          setUsername(e.target.value)
          setServerFields((prev) => without(prev, 'username'))
        }}
        error={usernameMsg}
        hint={signup ? '3 to 20 letters, numbers or _. Only you see it.' : undefined}
      />
      <TextInput
        label="Password"
        type="password"
        value={password}
        autoComplete={signup ? 'new-password' : 'current-password'}
        maxLength={128}
        onChange={(e) => {
          setPassword(e.target.value)
          setServerFields((prev) => without(prev, 'password'))
        }}
        error={passwordMsg}
        hint={signup ? `At least ${C.PASSWORD_MIN_LENGTH} characters.` : undefined}
      />
      {error && (
        <p className="field__error" role="alert">
          {error}
        </p>
      )}
      <Button type="submit" block disabled={busy}>
        {busy ? (signup ? 'Creating account…' : 'Logging in…') : signup ? 'Create account' : 'Log in'}
      </Button>
    </form>
  )
}
