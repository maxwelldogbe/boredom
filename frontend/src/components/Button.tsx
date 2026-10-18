import type { ButtonHTMLAttributes } from 'react'

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'danger' | 'ghost'
  block?: boolean
}

/** Shared button: min height var(--tap), one primary action per screen. */
export function Button({ variant = 'primary', block = false, className = '', type = 'button', ...rest }: ButtonProps) {
  const classes = ['btn', `btn--${variant}`, block ? 'btn--block' : '', className].filter(Boolean).join(' ')
  return <button type={type} className={classes} {...rest} />
}
