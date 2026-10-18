import type { ReactNode } from 'react'

interface EmptyStateProps {
  icon?: string
  title: string
  children?: ReactNode
  actions?: ReactNode
}

/** Centered message for empty, error and waiting screens. */
export function EmptyState({ icon, title, children, actions }: EmptyStateProps) {
  return (
    <section className="empty">
      {icon && (
        <div className="empty__icon" aria-hidden="true">
          {icon}
        </div>
      )}
      <h2 className="empty__title">{title}</h2>
      {children && <div className="empty__body">{children}</div>}
      {actions && <div className="empty__actions">{actions}</div>}
    </section>
  )
}

/** Loading state with a text label (no animation needed). */
export function Loading({ label = 'Loading…' }: { label?: string }) {
  return (
    <p className="loading" role="status">
      <span aria-hidden="true">⏳ </span>
      {label}
    </p>
  )
}
