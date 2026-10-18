import { useEffect } from 'react'
import { useRoomActions, useRoomState } from '../state/context'
import type { Toast } from '../state/roomReducer'

const TOAST_MS = 3500

function ToastItem({ toast, onDone }: { toast: Toast; onDone: (id: number) => void }) {
  useEffect(() => {
    const timer = setTimeout(() => onDone(toast.id), TOAST_MS)
    return () => clearTimeout(timer)
  }, [toast.id, onDone])
  return (
    <div className={`toast toast--${toast.tone}`} role={toast.tone === 'error' ? 'alert' : 'status'}>
      {toast.tone === 'error' ? '⚠️ ' : ''}
      {toast.message}
    </div>
  )
}

/** Renders the provider's toasts at the bottom of the screen. */
export function ToastHost() {
  const { toasts } = useRoomState()
  const { dismissToast } = useRoomActions()
  return (
    <div className="toasts" aria-live="polite">
      {toasts.map((t) => (
        <ToastItem key={t.id} toast={t} onDone={dismissToast} />
      ))}
    </div>
  )
}
