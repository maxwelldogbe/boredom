/** Small building blocks for the Nemesis console pages. */
import { useId, type InputHTMLAttributes, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import type { MoneyPermission } from '../api'
import { useAdminSession } from '../session'
import type { Person } from './types'

/** Money pages need a two-factor session and (optionally) a permission. */
export function MoneyGate({ permission, children }: { permission?: MoneyPermission; children: ReactNode }) {
  const { session } = useAdminSession()
  const money = session.money
  if (!money?.verified)
    return (
      <div className="stack">
        <p role="alert" className="field__error">
          Money tools need two-factor. <Link to="/admin/security">Set it up on the Security page</Link>, then log in again
          with a code.
        </p>
      </div>
    )
  if (permission && !money.permissions.includes(permission))
    return (
      <p role="alert" className="field__error">
        You don't have permission for this page.
      </p>
    )
  return <>{children}</>
}

export function PersonText({ person }: { person: Person | null }) {
  if (!person) return <span className="muted">Deleted account</span>
  return (
    <Link to={`/admin/users/u/${person.userId}`}>
      {person.nickname}
      {person.tag ? <span className="muted"> #{person.tag}</span> : null}
    </Link>
  )
}

export function Field({
  label,
  error,
  ...rest
}: { label: string; error?: string | null } & Omit<InputHTMLAttributes<HTMLInputElement>, 'id'>) {
  const id = useId()
  return (
    <div className="field">
      <label htmlFor={id} className="field__label">
        {label}
      </label>
      <input id={id} className="field__input" aria-invalid={error ? true : undefined} {...rest} />
      {error && (
        <p className="field__error" role="alert">
          {error}
        </p>
      )}
    </div>
  )
}

export function ErrorText({ message }: { message: string | null }) {
  return message ? (
    <p className="field__error" role="alert">
      {message}
    </p>
  ) : null
}

export function StatusFilter({ value, options, onChange }: { value: string; options: Array<[string, string]>; onChange: (v: string) => void }) {
  return (
    <div className="segmented" role="radiogroup" aria-label="Status">
      {options.map(([key, label]) => (
        <button key={key} type="button" role="radio" aria-checked={key === value} className="segmented__option" onClick={() => onChange(key)}>
          {label}
        </button>
      ))}
    </div>
  )
}

export function Dl({ rows }: { rows: Array<[string, ReactNode]> }) {
  return (
    <dl className="money-dl">
      {rows.map(([k, v]) => (
        <div key={k}>
          <dt>{k}</dt>
          <dd>{v}</dd>
        </div>
      ))}
    </dl>
  )
}
