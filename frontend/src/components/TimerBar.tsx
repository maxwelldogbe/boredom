import { useRemainingMs } from '../state/useCountdown'

interface TimerBarProps {
  deadline: number | null
  totalMs: number
  label?: string
}

/** Horizontal bar shrinking toward a server deadline, with seconds left as text. */
export function TimerBar({ deadline, totalMs, label = 'Time left' }: TimerBarProps) {
  const remaining = useRemainingMs(deadline)
  if (remaining === null) return null
  const fraction = Math.max(0, Math.min(1, remaining / totalMs))
  const seconds = Math.ceil(remaining / 1000)
  return (
    <div className="timer-bar" role="timer" aria-label={`${label}: ${seconds} seconds`}>
      <div className="timer-bar__track">
        <div
          className={`timer-bar__fill${seconds <= 3 ? ' timer-bar__fill--low' : ''}`}
          style={{ width: `${fraction * 100}%` }}
        />
      </div>
      <span className="timer-bar__text">{seconds}s</span>
    </div>
  )
}
