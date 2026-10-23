import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Button } from '../components/Button'
import { Logo } from '../components/Logo'
import { PlayerChip } from '../components/PlayerChip'
import { RoomCodeInput } from '../components/RoomCodeInput'
import { friendlyError } from '../lib/errors'
import { getProfile } from '../lib/profileStore'
import { isRoomCode } from '../lib/roomCode'
import { SLOW_SERVER_MESSAGE, withSlowNotice } from '../lib/slow'
import { useRoomActions, useRoomState } from '../state/context'

/** Create a room, or join one with a 4-letter code. */
export default function HomePage() {
  const navigate = useNavigate()
  const { createRoom, joinRoom } = useRoomActions()
  const { seatLost } = useRoomState()
  const [profile] = useState(() => getProfile())
  const [joining, setJoining] = useState(false)
  const [code, setCode] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [slow, setSlow] = useState(false)

  const create = async () => {
    if (!profile) return navigate('/setup?next=%2F')
    setBusy(true)
    setError(null)
    try {
      const roomCode = await withSlowNotice(createRoom, setSlow)
      navigate(`/room/${roomCode}`)
    } catch (err) {
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

      {!joining ? (
        <div className="stack home__actions">
          <Button block onClick={create} disabled={busy}>
            {busy ? 'Creating room…' : 'Create room'}
          </Button>
          <Button
            variant="secondary"
            block
            onClick={() => {
              setJoining(true)
              setError(null)
            }}
            disabled={busy}
          >
            Join room
          </Button>
        </div>
      ) : (
        <form className="stack home__actions" onSubmit={join} noValidate>
          <h2 className="home__join-title">Enter the room code</h2>
          <RoomCodeInput value={code} onChange={setCode} disabled={busy} invalid={Boolean(error)} />
          <Button type="submit" block disabled={busy || code.length < 4}>
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
      {!joining && (
        <p className="home__account-link">
          {!profile ? (
            <Link to="/setup?mode=login">Have an account? Log in</Link>
          ) : profile.type === 'guest' ? (
            <Link to="/profile">Save your profile with a free account</Link>
          ) : null}
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
