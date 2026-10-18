import { useRemainingMs } from '../state/useCountdown'

interface CountdownRingProps {
  deadline: number | null
  totalMs: number
  size?: number
}

/** Circular countdown with the seconds left in the middle (inline SVG). */
export function CountdownRing({ deadline, totalMs, size = 64 }: CountdownRingProps) {
  const remaining = useRemainingMs(deadline)
  if (remaining === null) return null
  const r = 26
  const circumference = 2 * Math.PI * r
  const fraction = Math.max(0, Math.min(1, remaining / totalMs))
  const seconds = Math.ceil(remaining / 1000)
  return (
    <div className="ring" role="timer" aria-label={`${seconds} seconds left`}>
      <svg width={size} height={size} viewBox="0 0 64 64" aria-hidden="true">
        <circle cx="32" cy="32" r={r} className="ring__track" />
        <circle
          cx="32"
          cy="32"
          r={r}
          className={`ring__fill${seconds <= 3 ? ' ring__fill--low' : ''}`}
          strokeDasharray={circumference}
          strokeDashoffset={circumference * (1 - fraction)}
          transform="rotate(-90 32 32)"
        />
      </svg>
      <span className="ring__text">{seconds}</span>
    </div>
  )
}
