import { useState, type FormEvent } from 'react'
import { Button } from '../../components/Button'
import { QrCode } from '../../pages/room/QrCode'
import { AdminApiError, adminSend } from '../api'
import { useAdminSession } from '../session'

type Setup = { secret: string; otpauthUri: string }

/** Two-factor enrolment: secret and QR, confirm with a code, then the backup codes (once). */
export default function SecurityPage() {
  const { session, refresh } = useAdminSession()
  const [setup, setSetup] = useState<Setup | null>(null)
  const [code, setCode] = useState('')
  const [codes, setCodes] = useState<string[] | null>(null)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const enrolled = session.money?.enrolled ?? false

  const call = async <T,>(fn: () => Promise<T>): Promise<T | null> => {
    setBusy(true)
    setError(null)
    try {
      return await fn()
    } catch (err) {
      setError(err instanceof AdminApiError ? err.message : 'Something went wrong.')
      return null
    } finally {
      setBusy(false)
    }
  }

  const start = async () => {
    const data = await call(() => adminSend<Setup>('2fa/setup', session.csrfToken))
    if (data) setSetup(data)
  }

  const confirm = async (e: FormEvent) => {
    e.preventDefault()
    const data = await call(() => adminSend<{ backupCodes: string[] }>('2fa/confirm', session.csrfToken, { code: code.trim() }))
    if (data) setCodes(data.backupCodes)
  }

  if (codes)
    return (
      <div className="stack">
        <h1>Security</h1>
        <section className="card stack" aria-labelledby="backup-codes">
          <h2 id="backup-codes">Your backup codes</h2>
          <p>Each code works once, if you lose your phone. They will not be shown again.</p>
          <ul className="backup-codes mono">
            {codes.map((c) => (
              <li key={c}>{c}</li>
            ))}
          </ul>
          <label className="check">
            <input type="checkbox" checked={saved} onChange={(e) => setSaved(e.target.checked)} />I saved these codes somewhere safe
          </label>
          <Button disabled={!saved} onClick={refresh}>
            Done
          </Button>
        </section>
      </div>
    )

  return (
    <div className="stack">
      <h1>Security</h1>
      {enrolled ? (
        <section className="card stack">
          <h2>Two-factor is on</h2>
          <p className="muted">You enter a code from your authenticator app when you log in and before money actions.</p>
        </section>
      ) : (
        <section className="card stack" aria-labelledby="twofa">
          <h2 id="twofa">Set up two-factor</h2>
          <p className="muted">Money and ID tools need two-factor. Use any authenticator app (TOTP).</p>
          {!setup ? (
            <Button onClick={() => void start()} disabled={busy}>
              Start setup
            </Button>
          ) : (
            <form className="stack" onSubmit={confirm} noValidate>
              <QrCode url={setup.otpauthUri} />
              <p>
                Or enter this key: <span className="mono">{setup.secret}</span>
              </p>
              <p className="small muted mono break">{setup.otpauthUri}</p>
              <label className="field">
                <span className="field__label">Code from the app</span>
                <input className="field__input" inputMode="numeric" autoComplete="one-time-code" value={code} onChange={(e) => setCode(e.target.value)} />
              </label>
              <Button type="submit" disabled={busy || !code.trim()}>
                Turn on two-factor
              </Button>
            </form>
          )}
        </section>
      )}
      {error && (
        <p className="field__error" role="alert">
          {error}
        </p>
      )}
    </div>
  )
}
