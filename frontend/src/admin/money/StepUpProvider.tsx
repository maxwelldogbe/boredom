/** The step-up dialog: shown whenever the server answers STEP_UP_REQUIRED, then the action is
 *  retried with the fresh step-up. Cancelling rejects the action with the original error. */
import { useCallback, useMemo, useRef, useState, type FormEvent, type ReactNode } from 'react'
import { Button } from '../../components/Button'
import { Modal } from '../../components/Modal'
import { AdminApiError, adminSend } from '../api'
import { useAdminSession } from '../session'
import { StepUpContext, type StepUp } from './stepUpContext'

interface Pending {
  resolve: () => void
  reject: () => void
}

export function StepUpProvider({ children }: { children: ReactNode }) {
  const { session } = useAdminSession()
  const [pending, setPending] = useState<Pending | null>(null)
  const pendingRef = useRef<Pending | null>(null)

  const ask = useCallback(
    () =>
      new Promise<void>((resolve, reject) => {
        const next = { resolve, reject }
        pendingRef.current = next
        setPending(next)
      }),
    [],
  )

  const run = useCallback<StepUp['run']>(
    async (action) => {
      try {
        return await action()
      } catch (err) {
        if (!(err instanceof AdminApiError && err.code === 'STEP_UP_REQUIRED')) throw err
        try {
          await ask()
        } catch {
          throw err
        }
        return action()
      }
    },
    [ask],
  )

  const value = useMemo(() => ({ run }), [run])
  const close = (ok: boolean) => {
    const current = pendingRef.current
    pendingRef.current = null
    setPending(null)
    if (ok) current?.resolve()
    else current?.reject()
  }

  return (
    <StepUpContext.Provider value={value}>
      {children}
      {pending && <StepUpDialog csrfToken={session.csrfToken} onDone={() => close(true)} onCancel={() => close(false)} />}
    </StepUpContext.Provider>
  )
}

function StepUpDialog({ csrfToken, onDone, onCancel }: { csrfToken: string; onDone: () => void; onCancel: () => void }) {
  const [code, setCode] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const submit = async (e?: FormEvent) => {
    e?.preventDefault()
    if (!code.trim()) return setError('Enter the 6-digit code from your app.')
    setBusy(true)
    try {
      await adminSend('2fa/step-up', csrfToken, { code: code.trim() })
      onDone()
    } catch (err) {
      setBusy(false)
      setError(err instanceof AdminApiError ? err.message : 'Something went wrong.')
    }
  }

  return (
    <Modal
      title="Confirm it's you"
      onClose={onCancel}
      closeOnBackdrop={false}
      actions={
        <>
          <Button block disabled={busy} onClick={() => void submit()}>
            {busy ? 'Checking…' : 'Confirm'}
          </Button>
          <Button variant="secondary" block onClick={onCancel} disabled={busy}>
            Cancel
          </Button>
        </>
      }
    >
      <form className="stack" onSubmit={submit} noValidate>
        <p className="muted">This action needs a fresh code from your authenticator app.</p>
        <label className="field">
          <span className="field__label">Code</span>
          <input
            className="field__input"
            inputMode="numeric"
            autoComplete="one-time-code"
            value={code}
            onChange={(e) => {
              setCode(e.target.value)
              setError(null)
            }}
            data-autofocus
          />
        </label>
        {error && (
          <p className="field__error" role="alert">
            {error}
          </p>
        )}
      </form>
    </Modal>
  )
}
