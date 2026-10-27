import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { Button } from '../components/Button'
import { EmptyState, Loading } from '../components/EmptyState'
import { LockWall } from '../components/LockWall'
import { Logo } from '../components/Logo'
import { C } from '../lib/constants'
import { errorCode, friendlyError } from '../lib/errors'
import { isRoomCode } from '../lib/roomCode'
import { SLOW_SERVER_MESSAGE, withSlowNotice } from '../lib/slow'
import { useRoomActions } from '../state/context'
import { useGuestQuota } from '../state/guestQuotaContext'

type JoinStatus = 'joining' | 'notFound' | 'full' | 'inProgress' | 'error'

/** Invite landing (/join/:code): peek for the host's name, then join and enter the room. */
export default function JoinPage() {
  const navigate = useNavigate()
  const code = (useParams().code ?? '').toUpperCase()
  const { peek, joinRoom } = useRoomActions()
  const [status, setStatus] = useState<JoinStatus>('joining')
  const [hostName, setHostName] = useState<string | null>(null)
  const [message, setMessage] = useState('')
  const [slow, setSlow] = useState(false)
  const [attempt, setAttempt] = useState(0)
  const started = useRef<string | null>(null)
  const valid = isRoomCode(code)
  const { locked, refresh, handleError } = useGuestQuota()

  useEffect(() => refresh(), [refresh])

  useEffect(() => {
    const key = `${code}#${attempt}`
    if (!valid || started.current === key) return // StrictMode runs effects twice
    started.current = key
    withSlowNotice(async () => {
      const info = await peek(code)
      setHostName(info.hostNickname)
      if (!info.exists) {
        setStatus('notFound')
        return
      }
      await joinRoom(code)
      navigate(`/room/${code}`, { replace: true })
    }, setSlow).catch((err: unknown) => {
      handleError(err)
      const c = errorCode(err)
      setMessage(friendlyError(err, code))
      setStatus(
        c === 'ROOM_NOT_FOUND' ? 'notFound' : c === 'ROOM_FULL' ? 'full' : c === 'GAME_IN_PROGRESS' ? 'inProgress' : 'error',
      )
    })
  }, [code, valid, attempt, peek, joinRoom, navigate, handleError])

  const home = (
    <Button variant="secondary" block onClick={() => navigate('/')}>
      Go home
    </Button>
  )
  const retry = (
    <Button
      block
      onClick={() => {
        setStatus('joining')
        setAttempt((n) => n + 1)
      }}
    >
      Retry
    </Button>
  )

  const brand = <Logo size={32} className="join__logo" />

  if (!valid) {
    return (
      <main className="page">
        {brand}
        <EmptyState icon="🤔" title="That doesn't look like a room code" actions={home}>
          Room codes are {C.ROOM_CODE_LENGTH} letters, like ABCD.
        </EmptyState>
      </main>
    )
  }

  if (locked) {
    return (
      <main className="page">
        {brand}
        <LockWall />
      </main>
    )
  }

  return (
    <main className="page">
      {brand}
      {status === 'joining' && (
        <>
          <h1>{hostName ? `Joining ${hostName}'s room` : `Joining room ${code}`}</h1>
          <Loading label="Joining…" />
          {slow && <p className="notice">{SLOW_SERVER_MESSAGE}</p>}
        </>
      )}
      {status === 'notFound' && (
        <EmptyState
          icon="🔍"
          title={`Room ${code} not found`}
          actions={
            <>
              <Button block onClick={() => navigate('/')}>
                Try another code
              </Button>
              <Button variant="secondary" block onClick={() => navigate('/')}>
                Create a room
              </Button>
            </>
          }
        >
          We couldn't find room {code}. Check the code or ask the host for a new link.
        </EmptyState>
      )}
      {status === 'full' && (
        <EmptyState icon="🚪" title="Room is full" actions={home}>
          {message}
        </EmptyState>
      )}
      {status === 'inProgress' && (
        <EmptyState icon="🎮" title="Game in progress" actions={<>{retry}{home}</>}>
          {message}
        </EmptyState>
      )}
      {status === 'error' && (
        <EmptyState icon="⚠️" title="Couldn't join" actions={<>{retry}{home}</>}>
          {message}
        </EmptyState>
      )}
    </main>
  )
}
