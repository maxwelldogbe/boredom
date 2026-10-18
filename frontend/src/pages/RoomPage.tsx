import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { Button } from '../components/Button'
import { EmptyState, Loading } from '../components/EmptyState'
import { friendlyError } from '../lib/errors'
import { getRoomToken } from '../lib/roomTokens'
import { useRoomActions, useRoomState } from '../state/context'
import { FinalResults } from './room/FinalResults'
import { GameScreen } from './room/GameScreen'
import { Lobby } from './room/Lobby'
import { TopBar } from './room/TopBar'

/** /room/:code: rejoins by token after a refresh, then shows lobby, game or results. */
export default function RoomPage() {
  const navigate = useNavigate()
  const code = (useParams().code ?? '').toUpperCase()
  const state = useRoomState()
  const { joinRoom } = useRoomActions()
  const [error, setError] = useState<string | null>(null)
  const [attempt, setAttempt] = useState(0)
  const started = useRef<string | null>(null)
  const leaving = useRef(false)
  const inRoom = state.room?.code === code && state.playerId !== null

  useEffect(() => {
    const key = `${code}#${attempt}`
    if (inRoom || state.seatLost || leaving.current || started.current === key) return
    started.current = key
    if (!getRoomToken(code)) {
      navigate(`/join/${code}`, { replace: true })
      return
    }
    joinRoom(code).catch((err: unknown) => setError(friendlyError(err, code)))
  }, [code, inRoom, state.seatLost, attempt, joinRoom, navigate])

  const goHome = (
    <Button variant="secondary" block onClick={() => navigate('/')}>
      Go home
    </Button>
  )

  if (state.seatLost && !inRoom) {
    return (
      <main className="page">
        <EmptyState icon="👋" title="You're no longer in this room" actions={goHome}>
          {state.seatLost}
        </EmptyState>
      </main>
    )
  }
  if (error && !inRoom) {
    return (
      <main className="page">
        <EmptyState
          icon="⚠️"
          title="Couldn't get back into the room"
          actions={
            <>
              <Button
                block
                onClick={() => {
                  setError(null)
                  setAttempt((n) => n + 1)
                }}
              >
                Retry
              </Button>
              {goHome}
            </>
          }
        >
          {error}
        </EmptyState>
      </main>
    )
  }
  if (!inRoom || !state.room || !state.playerId) {
    return (
      <main className="page">
        <Loading label={`Joining room ${code}…`} />
      </main>
    )
  }

  const room = state.room
  return (
    <main className="page room">
      <TopBar
        room={room}
        me={state.playerId}
        onLeft={() => navigate('/', { replace: true })}
        onLeaving={() => {
          leaving.current = true
        }}
      />
      {state.connection !== 'connected' && (
        <p className="notice" role="status">
          Reconnecting… your seat is kept.
        </p>
      )}
      {room.status === 'lobby' && <Lobby room={room} me={state.playerId} />}
      {(room.status === 'playing' || room.status === 'between_rounds') && (
        <GameScreen room={room} me={state.playerId} />
      )}
      {room.status === 'finished' && <FinalResults room={room} me={state.playerId} />}
    </main>
  )
}
