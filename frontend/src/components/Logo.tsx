import type { CSSProperties } from 'react'

interface LogoProps {
  /** `full` is mark + wordmark; `mark` is the face alone, for small spaces. */
  variant?: 'full' | 'mark'
  /** Mark height in px; the wordmark scales with it. */
  size?: number
  /** `auto` follows the color scheme (inverse mark in dark mode); `dark` forces the inverse mark for dark backgrounds. */
  tone?: 'auto' | 'light' | 'dark'
  className?: string
}

const MARK = '/boredom-mark.svg'
const MARK_INVERSE = '/boredom-mark-inverse.svg'

/** The boredom brand. The mark is never recolored or stretched: always square, always one of the two supplied files. */
export function Logo({ variant = 'full', size = 40, tone = 'auto', className }: LogoProps) {
  const full = variant === 'full'
  const src = tone === 'dark' ? MARK_INVERSE : MARK
  const img = <img className="logo__mark" src={src} alt={full ? '' : 'boredom'} width={size} height={size} />
  return (
    <span
      className={['logo', tone === 'dark' && 'logo--on-dark', className].filter(Boolean).join(' ')}
      style={{ '--logo-size': `${size}px` } as CSSProperties}
    >
      {tone === 'auto' ? (
        <picture>
          <source srcSet={MARK_INVERSE} media="(prefers-color-scheme: dark)" />
          {img}
        </picture>
      ) : (
        img
      )}
      {full && <span className="logo__word">boredom</span>}
    </span>
  )
}
