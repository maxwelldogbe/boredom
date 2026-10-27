/** Confirmation and report dialogs shared by the friends page, recent players and room menus.
 *  Focus starts on Cancel, so a stray Enter never removes, blocks or reports anyone. */
import { useId, useState, type ReactNode } from 'react'
import { C } from '../lib/constants'
import { REASON_LABELS, REPORT_REASONS, socialError } from '../lib/social'
import type { ReportReason } from '../types/protocol'
import { Button } from './Button'
import { Modal } from './Modal'

export function ConfirmDialog({
  title,
  children,
  confirmLabel,
  onConfirm,
  onClose,
}: {
  title: string
  children: ReactNode
  confirmLabel: string
  /** Resolve to close; throw to show the error and stay open. */
  onConfirm: () => Promise<void>
  onClose: () => void
}) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const confirm = async () => {
    setBusy(true)
    setError(null)
    try {
      await onConfirm()
      onClose()
    } catch (err) {
      setError(socialError(err))
      setBusy(false)
    }
  }
  return (
    <Modal
      title={title}
      onClose={onClose}
      actions={
        <>
          <Button variant="danger" block disabled={busy} onClick={() => void confirm()}>
            {busy ? 'Working…' : confirmLabel}
          </Button>
          <Button variant="secondary" block onClick={onClose} disabled={busy} data-autofocus>
            Cancel
          </Button>
        </>
      }
    >
      {children}
      {error && (
        <p className="field__error" role="alert">
          {error}
        </p>
      )}
    </Modal>
  )
}

export function ReportDialog({
  nickname,
  onSubmit,
  onClose,
}: {
  nickname: string
  onSubmit: (reason: ReportReason, note: string) => Promise<void>
  onClose: () => void
}) {
  const [reason, setReason] = useState<ReportReason | null>(null)
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const noteId = useId()
  const counterId = useId()
  const submit = async () => {
    if (!reason) return setError('Pick a reason.')
    setBusy(true)
    setError(null)
    try {
      await onSubmit(reason, note)
      onClose()
    } catch (err) {
      setError(socialError(err))
      setBusy(false)
    }
  }
  return (
    <Modal
      title={`Report ${nickname}`}
      onClose={onClose}
      actions={
        <>
          <Button variant="danger" block disabled={busy || !reason} onClick={() => void submit()}>
            {busy ? 'Sending…' : 'Send report'}
          </Button>
          <Button variant="secondary" block onClick={onClose} disabled={busy} data-autofocus>
            Cancel
          </Button>
        </>
      }
    >
      <p>Only our team sees reports. {nickname} is not told who reported them.</p>
      <fieldset className="report__reasons">
        <legend>What happened?</legend>
        {REPORT_REASONS.map((r) => (
          <label key={r} className="report__reason">
            <input type="radio" name="report-reason" value={r} checked={reason === r} onChange={() => setReason(r)} />
            {REASON_LABELS[r]}
          </label>
        ))}
      </fieldset>
      <div className="field">
        <label className="field__label" htmlFor={noteId}>
          Anything else? (optional)
        </label>
        <textarea
          id={noteId}
          className="field__input report__note"
          rows={3}
          maxLength={C.REPORT_NOTE_MAX}
          value={note}
          aria-describedby={counterId}
          onChange={(e) => setNote(e.target.value)}
        />
        <span id={counterId} className="field__hint" aria-live="polite">
          {note.length}/{C.REPORT_NOTE_MAX}
        </span>
      </div>
      {error && (
        <p className="field__error" role="alert">
          {error}
        </p>
      )}
    </Modal>
  )
}
