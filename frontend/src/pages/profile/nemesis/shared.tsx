/** Shared pieces of the Nemesis section: loading, errors, money text and a confirm dialog. */
import type { ReactNode } from 'react'
import { Button } from '../../../components/Button'
import { Modal } from '../../../components/Modal'
import { LoadError } from '../ProfileSections'
import type { Load } from '../useLoad'

export function Skeleton({ label }: { label: string }) {
  return (
    <div className="skeleton" role="status" aria-label={label}>
      <span className="skeleton__line" aria-hidden="true" />
      <span className="skeleton__line" aria-hidden="true" />
    </div>
  )
}

/** Loading skeleton, error with Retry, or the content. */
export function Loaded<T>({ load, label, onRetry, children }: { load: Load<T>; label: string; onRetry: () => void; children: (data: T) => ReactNode }) {
  if (load.status === 'loading') return <Skeleton label={label} />
  if (load.status === 'error') return <LoadError message={load.message} onRetry={onRetry} />
  return <>{children(load.data)}</>
}

export function FormError({ message }: { message: string | null }) {
  return message ? (
    <p className="field__error" role="alert">
      {message}
    </p>
  ) : null
}

/** A confirmation whose safe choice (Cancel) has the focus. */
export function Confirm({
  title,
  children,
  confirmLabel,
  danger = false,
  busy = false,
  onConfirm,
  onClose,
}: {
  title: string
  children: ReactNode
  confirmLabel: string
  danger?: boolean
  busy?: boolean
  onConfirm: () => void
  onClose: () => void
}) {
  return (
    <Modal
      title={title}
      onClose={onClose}
      actions={
        <>
          <Button variant={danger ? 'danger' : 'primary'} block disabled={busy} onClick={onConfirm}>
            {busy ? 'Please wait…' : confirmLabel}
          </Button>
          <Button variant="secondary" block onClick={onClose} disabled={busy} data-autofocus>
            Cancel
          </Button>
        </>
      }
    >
      {children}
    </Modal>
  )
}

export function BackButton({ onBack }: { onBack: () => void }) {
  return (
    <Button variant="ghost" onClick={onBack} className="nemesis__back">
      ← Back
    </Button>
  )
}
