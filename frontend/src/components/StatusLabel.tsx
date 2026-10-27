import { STATUS_LABELS } from '../lib/social'
import type { FriendStatus } from '../types/protocol'

/** A friend's status as an icon plus words (never color alone). */
export function StatusLabel({ status }: { status: FriendStatus }) {
  const { icon, label } = STATUS_LABELS[status]
  return (
    <span className={`status-label status-label--${status}`}>
      <span className="status-label__icon" aria-hidden="true">
        {icon}
      </span>
      {label}
    </span>
  )
}
