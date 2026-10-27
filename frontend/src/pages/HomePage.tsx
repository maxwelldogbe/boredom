import { useEffect, useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Button } from '../components/Button'
import { CommunityLink } from '../components/CommunityLink'
import { OnlineFriends } from '../components/Invites'
import { LockWall } from '../components/LockWall'
import { Logo } from '../components/Logo'
import { PlayerChip } from '../components/PlayerChip'
import { RoomCodeInput } from '../components/RoomCodeInput'
import { friendlyError } from '../lib/errors'
import { getProfile } from '../lib/profileStore'
import { isRoomCode } from '../lib/roomCode'
import { SLOW_SERVER_MESSAGE, withSlowNotice } from '../lib/slow'
import { useRoomActions, useRoomState } from '../state/context'
import { useGuestQuota } from '../state/guestQuotaContext'
import { useSocial } from '../state/socialContext'

/** Create a room, or join one with a 4-letter code. */
export default function HomePage() {
  const navigate = useNavigate()
  const { createRoom, joinRoom } = useRoomActions()
  const { seatLost } = useRoomState()
  const { signedIn, incomingCount } = useSocial()
  const [profile] = useState(() => getProfile())
  const [joining, setJoining] = useState(false)
  const [code, setCode] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [slow, setSlow] = useState(false)
  const { locked, refresh, handleError } = useGuestQuota()

  useEffect(() => {
    if (profile) refresh()
  }, [profile, refresh])

  const create = async () => {
    if (!profile) return navigate('/setup?next=%2F')
    setBusy(true)
    setError(null)
    try {
      const roomCode = await withSlowNotice(createRoom, setSlow)
      navigate(`/room/${roomCode}`)
    } catch (err) {
      handleError(err)
      setError(friendlyError(err))
      setBusy(false)
    }
  }

  const join = async (e?: FormEvent) => {
    e?.preventDefault()
    if (!isRoomCode(code)) {
      setError("That doesn't look like a room code.")
      return
    }
    if (!profile) return navigate(`/setup?next=${encodeURIComponent(`/join/${code}`)}`)
    setBusy(true)
    setError(null)
    try {
      await withSlowNotice(() => joinRoom(code), setSlow)
      navigate(`/room/${code}`)
    } catch (err) {
      handleError(err)
      setError(friendlyError(err, code))
      setBusy(false)
    }
  }

  return (
    <main className="page home">
      <header className="home__header">
        <h1 className="home__title">
          <Logo size={44} />
        </h1>
        <Link to={profile ? '/profile' : '/setup'} className="home__profile" aria-label="Your profile">
          {profile ? <PlayerChip player={profile} size="sm" /> : 'Set up profile'}
        </Link>
      </header>
      <p className="muted">Party games for friends. One room code, everyone on their phone.</p>

      {seatLost && (
        <p className="notice" role="status">
          {seatLost}
        </p>
      )}

      {locked && <LockWall />}
      {!joining ? (
        <div className="stack home__actions">
          <Button block onClick={create} disabled={busy || locked}>
            {busy ? 'Creating room…' : 'Create room'}
          </Button>
          <Button
            variant="secondary"
            block
            onClick={() => {
              setJoining(true)
              setError(null)
            }}
            disabled={busy || locked}
          >
            Join room
          </Button>
        </div>
      ) : (
        <form className="stack home__actions" onSubmit={join} noValidate>
          <h2 className="home__join-title">Enter the room code</h2>
          <RoomCodeInput value={code} onChange={setCode} disabled={busy} invalid={Boolean(error)} />
          <Button type="submit" block disabled={busy || locked || code.length < 4}>
            {busy ? 'Joining…' : 'Join'}
          </Button>
          <Button
            variant="ghost"
            block
            onClick={() => {
              setJoining(false)
              setError(null)
              setCode('')
            }}
            disabled={busy}
          >
            Back
          </Button>
        </form>
      )}

      {error && (
        <p className="field__error" role="alert">
          {error}
        </p>
      )}
      {!joining && <CommunityLink note />}
      {!joining && <OnlineFriends />}
      {!joining && profile && (
        <Link to="/friends" className="btn btn--secondary btn--block home__friends">
          <span aria-hidden="true">👥 </span>
          Friends
          {signedIn && incomingCount > 0 && (
            <span className="count-badge" aria-label={`, ${incomingCount} new request${incomingCount === 1 ? '' : 's'}`}>
              {incomingCount}
            </span>
          )}
        </Link>
      )}
      {!joining && (
        <p className="home__account-link">
          {!profile ? (
            <Link to="/setup?mode=login">Have an account? Log in</Link>
          ) : profile.type === 'guest' ? (
            <Link to="/profile">Save your profile with a free account</Link>
          ) : null}
        </p>
      )}
      {!joining && (
        <p className="home__about">
          <Link to="/about">About boredom</Link>
        </p>
      )}
      {slow && (
        <p className="notice" role="status">
          {SLOW_SERVER_MESSAGE}
        </p>
      )}
    </main>
  )
}
