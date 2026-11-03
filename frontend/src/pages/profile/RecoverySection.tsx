import { useState, type FormEvent } from 'react'
import { Button } from '../../components/Button'
import { TextInput } from '../../components/TextInput'
import {
  AccountError,
  addRecoveryPhone,
  getAuthToken,
  removeRecoveryPhone,
  verifyRecoveryPhone,
} from '../../lib/account'
import { C } from '../../lib/constants'
import { useRoomActions } from '../../state/context'

/** A confirmed phone number for "Forgot password?" (PROTOCOL.md 8.8). Shown masked. */
export function RecoverySection({ phone: saved, onExpired }: { phone: string | null; onExpired: () => void }) {
  const { toast } = useRoomActions()
  const [phone, setPhone] = useState(saved)
  const [editing, setEditing] = useState(false)
  const [number, setNumber] = useState('')
  const [sentTo, setSentTo] = useState<string | null>(null)
  const [code, setCode] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const run = async (work: (token: string) => Promise<void>) => {
    const token = getAuthToken()
    if (!token) return onExpired()
    setBusy(true)
    setError(null)
    try {
      await work(token)
    } catch (err) {
      if (err instanceof AccountError && err.code === 'UNAUTHORIZED') onExpired()
      else setError(err instanceof AccountError ? (Object.values(err.fields)[0] ?? err.message) : 'Something went wrong.')
    } finally {
      setBusy(false)
    }
  }

  const send = (e?: FormEvent) => {
    e?.preventDefault()
    void run(async (token) => {
      const sent = await addRecoveryPhone(token, number)
      setSentTo(sent.phone)
      setCode('')
    })
  }

  const confirm = (e: FormEvent) => {
    e.preventDefault()
    void run(async (token) => {
      const done = await verifyRecoveryPhone(token, code)
      setPhone(done.phone)
      setEditing(false)
      setSentTo(null)
      setNumber('')
      toast('Recovery number saved.')
    })
  }

  const remove = () =>
    void run(async (token) => {
      await removeRecoveryPhone(token)
      setPhone(null)
      toast('Recovery number removed.')
    })

  return (
    <section className="card stack" aria-labelledby="recovery-heading">
      <h2 id="recovery-heading">Account recovery</h2>
      <p className="muted">
        {phone
          ? `If you forget your password, we text a code to ${phone}.`
          : 'Add a phone number so you can reset your password if you forget it. We only use it for that.'}
      </p>
      {!editing ? (
        <div className="stack">
          <Button variant="secondary" block onClick={() => setEditing(true)} disabled={busy}>
            {phone ? 'Change number' : 'Add phone number'}
          </Button>
          {phone && (
            <button type="button" className="text-button" onClick={remove} disabled={busy}>
              Remove number
            </button>
          )}
        </div>
      ) : sentTo === null ? (
        <form className="stack" onSubmit={send} noValidate>
          <TextInput
            label="Phone number"
            type="tel"
            value={number}
            autoComplete="tel"
            maxLength={20}
            onChange={(e) => setNumber(e.target.value)}
            hint="Like 024 000 0000, or with the country code: +233 24 000 0000."
          />
          <Button type="submit" block disabled={busy || !number.trim()}>
            {busy ? 'Sending…' : 'Send code'}
          </Button>
          <Button variant="ghost" block onClick={() => setEditing(false)} disabled={busy}>
            Cancel
          </Button>
        </form>
      ) : (
        <form className="stack" onSubmit={confirm} noValidate>
          <p role="status">
            We texted a {C.PHONE_CODE_LENGTH}-digit code to {sentTo}.
          </p>
          <TextInput
            label="Code"
            value={code}
            inputMode="numeric"
            autoComplete="one-time-code"
            maxLength={C.PHONE_CODE_LENGTH}
            onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))}
          />
          <Button type="submit" block disabled={busy || code.length !== C.PHONE_CODE_LENGTH}>
            {busy ? 'Checking…' : 'Confirm'}
          </Button>
          <Button variant="ghost" block onClick={() => setSentTo(null)} disabled={busy}>
            Use a different number
          </Button>
        </form>
      )}
      {error && (
        <p className="field__error" role="alert">
          {error}
        </p>
      )}
    </section>
  )
}
