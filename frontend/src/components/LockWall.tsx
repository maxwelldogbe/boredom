import { useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { FLYER } from '../config/guestPopup'
import { C } from '../lib/constants'
import { useGuestQuota } from '../state/guestQuotaContext'
import { useNow } from '../state/useCountdown'
import { Button } from './Button'

/** "1h 5m" until `until` (local ms), rounded up to the minute. */
function timeLeft(ms: number): string {
  const minutes = Math.max(1, Math.ceil(ms / 60_000))
  return `${Math.floor(minutes / 60)}h ${minutes % 60}m`
}

/** Shown to a guest who has used their free games: no dismiss, only Create account or Home.
 *  Renders nothing unless locked; it goes away by itself when the countdown ends. */
export function LockWall() {
  const { quota, locked } = useGuestQuota()
  const { pathname } = useLocation()
  const navigate = useNavigate()
  const now = useNow(1000)
  const [imageFailed, setImageFailed] = useState(false)
  if (!locked || !quota || quota.lockedUntil === null) return null
  const withImage = FLYER.src !== null && !imageFailed
  return (
    <section className="card stack lock-wall" aria-labelledby="lock-wall-title">
      {withImage && (
        <img className="guest-popup__flyer" src={FLYER.src!} alt={FLYER.alt} onError={() => setImageFailed(true)} />
      )}
      <h2 id="lock-wall-title">You've used your {quota.limit} games</h2>
      <p>Create a free account to keep playing. It takes a minute.</p>
      <Button block onClick={() => navigate(`/signup?next=${encodeURIComponent(pathname)}`)}>
        Create free account
      </Button>
      <p className="muted" role="timer">
        Games come back in {timeLeft(quota.lockedUntil - now)}
      </p>
      {pathname !== '/' && <Link to="/">Home</Link>}
    </section>
  )
}

/** "Games left: N" for guests with GUEST_QUOTA_SHOW_AT or fewer left; after the last one
 *  (on the results screen) "That was your last game for now." */
export function FreeGamesLeft({ results = false }: { results?: boolean }) {
  const { quota } = useGuestQuota()
  if (!quota || quota.remaining > C.GUEST_QUOTA_SHOW_AT) return null
  if (quota.remaining === 0) {
    return results ? <p className="notice free-games">That was your last game for now.</p> : null
  }
  return <p className="notice free-games">Games left: {quota.remaining}</p>
}
