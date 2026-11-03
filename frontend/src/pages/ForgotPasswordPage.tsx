import { useState, type FormEvent } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { Button } from '../components/Button'
import { TextInput } from '../components/TextInput'
import { AccountError, adoptSession, forgotPassword, resetPassword, submitRecoveryRequest } from '../lib/account'
import { C } from '../lib/constants'
import { safeNext } from '../lib/navigation'
import { useRoomActions } from '../state/context'

const failure = (err: unknown) => (err instanceof AccountError ? err.message : 'Something went wrong. Please try again.')

/** /forgot: a reset code by SMS to the account's recovery number, then a new password. */
export default function ForgotPasswordPage() {
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const { toast } = useRoomActions()
  const [step, setStep] = useState<'ask' | 'reset' | 'help' | 'helpSent'>('ask')
  const [help, setHelp] = useState({ phone: '', nickname: '', joined: '', friend: '', games: '', note: '' })
  const [login, setLogin] = useState('')
  const [code, setCode] = useState('')
  const [password, setPassword] = useState('')
  const [fields, setFields] = useState<Record<string, string>>({})
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const ask = async (e?: FormEvent) => {
    e?.preventDefault()
    if (!login.trim()) {
      setFields({ login: 'Enter your username or phone number.' })
      return
    }
    setBusy(true)
    setError(null)
    try {
      await forgotPassword(login.trim())
      setStep('reset')
    } catch (err) {
      setError(failure(err))
    } finally {
      setBusy(false)
    }
  }

  const reset = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    setFields({})
    try {
      const session = await resetPassword(login.trim(), code.trim(), password)
      const profile = adoptSession(session)
      toast(`Password changed. Welcome back, ${profile.nickname}!`)
      navigate(safeNext(params.get('next')), { replace: true })
    } catch (err) {
      if (err instanceof AccountError) setFields(err.fields)
      setError(failure(err))
      setBusy(false)
    }
  }

  const requestHelp = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    setFields({})
    try {
      const { phone, ...answers } = help
      await submitRecoveryRequest({ username: login.trim(), phone, answers })
      setStep('helpSent')
    } catch (err) {
      if (err instanceof AccountError) setFields(err.fields)
      setError(failure(err))
    } finally {
      setBusy(false)
    }
  }

  const helpField = (key: keyof typeof help, label: string, hint?: string, required = false) => (
    <TextInput
      label={required ? label : `${label} (optional)`}
      value={help[key]}
      maxLength={C.RECOVERY_ANSWER_MAX}
      onChange={(e) => setHelp((h) => ({ ...h, [key]: e.target.value }))}
      error={fields[key]}
      hint={hint}
      type={key === 'phone' ? 'tel' : 'text'}
    />
  )

  if (step === 'help' || step === 'helpSent') {
    return (
      <main className="page stack">
        <button type="button" className="text-button back-link" onClick={() => setStep('ask')}>
          ← Back
        </button>
        <h1>Ask us for help</h1>
        {step === 'helpSent' ? (
          <div className="stack" role="status">
            <p>Thanks. Our team will check your answers against the account.</p>
            <p>
              If they match, we'll text a code to the number you gave. Then come back to this page, choose "I already
              have a code", and enter it with your username and a new password. That number becomes your recovery
              number.
            </p>
            <Button block onClick={() => navigate('/', { replace: true })}>
              Go home
            </Button>
          </div>
        ) : (
          <form className="stack" onSubmit={requestHelp} noValidate>
            <p className="muted">
              No phone number on your account? Tell us what you remember. Our team compares it with the account before
              anything is sent, so only the real owner gets it back.
            </p>
            <TextInput
              label="Username"
              value={login}
              autoComplete="username"
              autoCapitalize="none"
              spellCheck={false}
              maxLength={20}
              onChange={(e) => setLogin(e.target.value)}
              error={fields.username}
            />
            {helpField('phone', 'Phone number for the code', 'Like 024 000 0000 or +233 24 000 0000.', true)}
            {helpField('nickname', 'The nickname you used', undefined, true)}
            {helpField('joined', 'When you made the account', 'For example: March 2026.')}
            {helpField('friend', "A friend's name or tag")}
            {helpField('games', 'Games you play most')}
            {helpField('note', 'Anything else that shows it is you')}
            {error && (
              <p className="field__error" role="alert">
                {error}
              </p>
            )}
            <Button type="submit" block disabled={busy}>
              {busy ? 'Sending…' : 'Send request'}
            </Button>
          </form>
        )}
      </main>
    )
  }

  return (
    <main className="page stack">
      <Link to="/setup?mode=login" className="back-link">
        ← Log in
      </Link>
      <h1>Reset your password</h1>
      {step === 'ask' ? (
        <form className="stack" onSubmit={ask} noValidate>
          <p className="muted">
            We'll text a code to the phone number saved on your account. If you never added one, we can't reset it this
            way.
          </p>
          <TextInput
            label="Username or phone number"
            value={login}
            autoComplete="username"
            autoCapitalize="none"
            spellCheck={false}
            maxLength={40}
            onChange={(e) => {
              setLogin(e.target.value)
              setFields({})
            }}
            error={fields.login}
          />
          {error && (
            <p className="field__error" role="alert">
              {error}
            </p>
          )}
          <Button type="submit" block disabled={busy}>
            {busy ? 'Sending…' : 'Send code'}
          </Button>
          <button
            type="button"
            className="text-button"
            onClick={() => {
              setError(null)
              setFields({})
              setStep('reset')
            }}
          >
            I already have a code
          </button>
          <button
            type="button"
            className="text-button"
            onClick={() => {
              setError(null)
              setFields({})
              setStep('help')
            }}
          >
            No phone number on your account? Ask us for help
          </button>
        </form>
      ) : (
        <form className="stack" onSubmit={reset} noValidate>
          <p className="muted" role="status">
            If that account has a phone number saved, a {C.PHONE_CODE_LENGTH}-digit code is on its way. It expires in{' '}
            {C.PHONE_CODE_TTL_MINUTES} minutes. A code from our team (after a help request) works here too.
          </p>
          <TextInput
            label="Username or phone number"
            value={login}
            autoComplete="username"
            autoCapitalize="none"
            spellCheck={false}
            maxLength={40}
            onChange={(e) => setLogin(e.target.value)}
          />
          <TextInput
            label="Code"
            value={code}
            inputMode="numeric"
            autoComplete="one-time-code"
            maxLength={C.PHONE_CODE_LENGTH}
            onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))}
            error={fields.code}
          />
          <TextInput
            label="New password"
            type="password"
            value={password}
            autoComplete="new-password"
            maxLength={128}
            onChange={(e) => setPassword(e.target.value)}
            error={fields.password}
            hint={`At least ${C.PASSWORD_MIN_LENGTH} characters.`}
          />
          {error && (
            <p className="field__error" role="alert">
              {error}
            </p>
          )}
          <Button type="submit" block disabled={busy || code.length !== C.PHONE_CODE_LENGTH || !password}>
            {busy ? 'Saving…' : 'Set new password'}
          </Button>
          <Button variant="ghost" block onClick={() => void ask()} disabled={busy}>
            Send a new code
          </Button>
        </form>
      )}
    </main>
  )
}
