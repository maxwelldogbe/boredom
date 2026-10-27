import { useEffect, useId, useRef, type ReactNode } from 'react'

interface ModalProps {
  title: string
  children: ReactNode
  onClose: () => void
  actions: ReactNode
  closeOnBackdrop?: boolean
  headerActions?: ReactNode
  /** Extra class on the backdrop, e.g. "modal--sheet" for a bottom sheet. */
  className?: string
  /** Keep the title for screen readers only (e.g. when an image says it). */
  hideTitle?: boolean
}

/** Accessible dialog: focus moves inside (to [data-autofocus] if present), traps focus, and
 *  closes with Escape. */
export function Modal({ title, children, onClose, actions, closeOnBackdrop = true, headerActions, className, hideTitle = false }: ModalProps) {
  const titleId = useId()
  const box = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null
    const dialog = box.current
    // A control marked data-autofocus (e.g. Cancel in a confirmation) wins; else the first one.
    const preferred = dialog?.querySelector<HTMLElement>('[data-autofocus]')
    ;(preferred ?? dialog?.querySelector<HTMLElement>('button, input, select, textarea, a[href], [tabindex]:not([tabindex="-1"])'))?.focus()
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault()
        onClose()
        return
      }
      if (e.key !== 'Tab' || !dialog) return
      const focusable = [...dialog.querySelectorAll<HTMLElement>('button, input, select, textarea, a[href], [tabindex]:not([tabindex="-1"])')].filter(
        (element) => !element.hasAttribute('disabled'),
      )
      if (focusable.length === 0) {
        e.preventDefault()
        dialog.focus()
        return
      }
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault()
        last.focus()
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault()
        first.focus()
      }
    }
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('keydown', onKey)
      previous?.focus?.()
    }
  }, [onClose])

  return (
    <div className={className ? `modal ${className}` : 'modal'} onMouseDown={(e) => closeOnBackdrop && e.target === e.currentTarget && onClose()}>
      <div className="modal__box" role="dialog" aria-modal="true" aria-labelledby={titleId} ref={box}>
        <div className="modal__header">
          <h2 id={titleId} className={hideTitle ? 'modal__title visually-hidden' : 'modal__title'}>
            {title}
          </h2>
          {headerActions && <div className="modal__header-actions">{headerActions}</div>}
        </div>
        <div className="modal__body">{children}</div>
        <div className="modal__actions">{actions}</div>
      </div>
    </div>
  )
}
