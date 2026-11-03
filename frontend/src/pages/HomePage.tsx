import { useEffect, useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { AlreadyInGameDialog } from '../components/AlreadyInGameDialog'
import { Button } from '../components/Button'
import { OnlineFriends } from '../components/Invites'
import { LockWall } from '../components/LockWall'
import { Logo } from '../components/Logo'
import { Modal } from '../components/Modal'
import { PlayerChip } from '../components/PlayerChip'
import { ReturnCard } from '../components/ReturnCard'
import { UiIcon } from '../components/UiIcon'
import { RoomCodeInput } from '../components/RoomCodeInput'
import { communityUrl } from '../config/community'
import { errorCode, friendlyError } from '../lib/errors'
import { getProfile } from '../lib/profileStore'
import { isRoomCode } from '../lib/roomCode'
import { SLOW_SERVER_MESSAGE, withSlowNotice } from '../lib/slow'
import { RequestError } from '../lib/socket'
import { useRoomActions, useRoomState } from '../state/context'
import { useGuestQuota } from '../state/guestQuotaContext'
import { useSocial } from '../state/socialContext'
import { useResumeSeat } from '../state/useResume'

type AccountCard = 'solo' | 'friends' | null

const ACCOUNT_TEXT: Record<'solo' | 'friends', string> = {
  solo: 'Solo games are for registered players. Create a free account.',
  friends: 'Friends are for registered players. Create a free account.',
}

/** Home: create a room (the one filled button), join or play alone, then quiet links. */
export default function HomePage() {
  const navigate = useNavigate()
  const { createRoom, joinRoom } = useRoomActions()
  const { seatLost, room } = useRoomState()
  const { signedIn, incomingCount } = useSocial()
  const [profile] = useState(() => getProfile())
  const [joining, setJoining] = useState(false)
  const [code, setCode] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [slow, setSlow] = useState(false)
  const [accountCard, setAccountCard] = useState<AccountCard>(null)
  const [inGame, setInGame] = useState<string | null>(null)
  const { locked, refresh, handleError } = useGuestQuota()
  const { seat, refresh: refreshSeat } = useResumeSeat()
  const registered = profile?.type === 'registered'
  const returning = seat !== null && room?.code !== seat.code
  const community = communityUrl()

  useEffect(() => {
    if (profile) refresh()
  }, [profile, refresh])

  const failed = (err: unknown, roomCode?: string) => {
    handleError(err)
    if (errorCode(err) === 'ALREADY_IN_GAME' && err instanceof RequestError) setInGame(String(err.data?.code ?? ''))
    setError(friendlyError(err, roomCode))
    setBusy(false)
  }

  const create = async () => {
    if (!profile) return navigate('/setup?next=%2F')
    setBusy(true)
    setError(null)
    try {
      const roomCode = await withSlowNotice(createRoom, setSlow)
      navigate(`/room/${roomCode}`)
    } catch (err) {
      failed(err)
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
      failed(err, code)
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
      <p className="muted home__tagline">Party games for friends. One room code, everyone on their phone.</p>

      {returning && seat && <ReturnCard seat={seat} onLeft={refreshSeat} />}

      {seatLost && (
        <p className="notice" role="status">
          {seatLost}
        </p>
      )}

      {locked && <LockWall />}
      {!joining ? (
        <div className="stack home__actions">
          <Button
            variant={returning ? 'secondary' : 'primary'}
            block
            className="home__create"
            onClick={create}
            disabled={busy || locked}
          >
            {busy ? 'Creating room…' : 'Create room'}
          </Button>
          <div className="home__pair">
            <Button
              variant="secondary"
              onClick={() => {
                setJoining(true)
                setError(null)
              }}
              disabled={busy || locked}
            >
              Join room
            </Button>
            {registered ? (
              <Link to="/solo" className="btn btn--secondary home__solo">
                <UiIcon name="robot" />
                Play alone
              </Link>
            ) : (
              <Button variant="secondary" className="home__solo" onClick={() => setAccountCard('solo')}>
                <UiIcon name="lock" />
                Play alone
              </Button>
            )}
          </div>
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

      {!joining && (
        <nav className="home__links" aria-label="More">
          {registered ? (
            <Link to="/friends" className="home__link">
              <UiIcon name="friends" />
              Friends
              {signedIn && incomingCount > 0 && (
                <span className="count-badge" aria-label={`, ${incomingCount} new request${incomingCount === 1 ? '' : 's'}`}>
                  {incomingCount}
                </span>
              )}
            </Link>
          ) : (
            <button type="button" className="home__link" onClick={() => setAccountCard('friends')}>
              <UiIcon name="friends" />
              Friends
            </button>
          )}
          {community && (
            <a
              className="home__link"
              href={community}
              target="_blank"
              rel="noopener noreferrer"
              aria-label="Community (opens in a new tab)"
            >
              <UiIcon name="chat" />
              Community
            </a>
          )}
        </nav>
      )}

      {!joining && <OnlineFriends />}

      {!joining && !registered && (
        <p className="card home__save">
          {!profile ? (
            <Link to="/setup?mode=login">Have an account? Log in</Link>
          ) : (
            <Link to="/profile">Save your profile with a free account</Link>
          )}
        </p>
      )}

      {slow && (
        <p className="notice" role="status">
          {SLOW_SERVER_MESSAGE}
        </p>
      )}
      {accountCard && (
        <Modal
          title={accountCard === 'solo' ? 'Play alone' : 'Friends'}
          onClose={() => setAccountCard(null)}
          actions={
            <>
              <Button block onClick={() => navigate(`/signup?next=${encodeURIComponent(accountCard === 'solo' ? '/solo' : '/friends')}`)}>
                Create account
              </Button>
              <Button
                variant="secondary"
                block
                onClick={() =>
                  navigate(
                    `/${profile ? 'profile' : 'setup'}?mode=login&next=${encodeURIComponent(accountCard === 'solo' ? '/solo' : '/friends')}`,
                  )
                }
              >
                Sign in
              </Button>
            </>
          }
        >
          <p>{ACCOUNT_TEXT[accountCard]}</p>
        </Modal>
      )}
      {inGame && <AlreadyInGameDialog code={inGame} onClose={() => setInGame(null)} />}
    </main>
  )
}
