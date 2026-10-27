import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { Button } from '../components/Button'
import { EmptyState, Loading } from '../components/EmptyState'
import { HowToPlayModal } from '../components/HowToPlayModal'
import { ReactionLayer } from '../components/Reactions'
import { gameInstructions, hasGameInstructions } from '../games/instructions'
import { C } from '../lib/constants'
import { friendlyError } from '../lib/errors'
import { getRoomToken } from '../lib/roomTokens'
import { useRoomActions, useRoomState } from '../state/context'
import { FinalResults } from './room/FinalResults'
import { ForfeitWaiting } from './room/ForfeitWaiting'
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
  const [manualInstructionsKey, setManualInstructionsKey] = useState<string | null>(null)
  const [autoOpenKey, setAutoOpenKey] = useState<string | null>(null)
  const seenInstructionKeys = useRef(new Set<string>())
  const instructionStateKey = useRef<string | null>(null)
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

  useEffect(() => {
    const room = state.room
    if (!room || room.status === 'playing') {
      instructionStateKey.current = null
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setAutoOpenKey(null)
      return
    }
    if (!room.selectedGame || !hasGameInstructions(room.selectedGame)) {
      instructionStateKey.current = null
      setAutoOpenKey(null)
      return
    }
    const key = `${room.code}:${room.selectedGame}`
    if (instructionStateKey.current === key) return
    instructionStateKey.current = key
    if (!seenInstructionKeys.current.has(key)) {
      seenInstructionKeys.current.add(key)
      setAutoOpenKey(key)
      return
    }
    setAutoOpenKey(null)
  }, [state.room])

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
  const selectedInstructionKey =
    room.selectedGame && hasGameInstructions(room.selectedGame) ? `${room.code}:${room.selectedGame}` : null
  const content = gameInstructions(room.selectedGame, {
    settings: room.settings,
    constants: C,
    playerCount: room.players.length,
  })
  const instructionsOpen =
    Boolean(
      selectedInstructionKey &&
        ((room.status !== 'playing' && autoOpenKey === selectedInstructionKey) ||
          (room.status !== 'playing' && manualInstructionsKey === selectedInstructionKey) ||
          manualInstructionsKey === `${selectedInstructionKey}:playing`),
    )

  const openInstructions = () => {
    if (selectedInstructionKey) {
      setManualInstructionsKey(room.status === 'playing' ? `${selectedInstructionKey}:playing` : selectedInstructionKey)
    }
  }

  const closeInstructions = () => {
    setAutoOpenKey(null)
    setManualInstructionsKey(null)
  }

  return (
    <main className="page room">
      <TopBar
        room={room}
        me={state.playerId}
        onLeft={() => navigate('/', { replace: true })}
        onLeaving={() => {
          leaving.current = true
        }}
        onHowToPlay={openInstructions}
      />
      {state.connection !== 'connected' && (
        <p className="notice" role="status">
          Reconnecting… your seat is kept.
        </p>
      )}
      {room.status === 'lobby' && <Lobby room={room} me={state.playerId} onHowToPlay={openInstructions} />}
      {(room.status === 'playing' || room.status === 'between_rounds') && (
        room.players.some((player) => player.id === state.playerId && player.inGame) ? (
          <GameScreen room={room} me={state.playerId} />
        ) : (
          <ForfeitWaiting room={room} me={state.playerId} />
        )
      )}
      {room.status === 'finished' && <FinalResults room={room} me={state.playerId} />}
      <ReactionLayer room={room} />
      {instructionsOpen && content && (
        <HowToPlayModal
          content={content}
          inGame={room.status !== 'lobby'}
          roundsToWin={Math.floor(Number(room.settings.bestOf ?? 3) / 2) + 1}
          pickSeconds={C.RPS_PICK_TIMEOUT_MS / 1000}
          offlineSeconds={C.OFFLINE_FORFEIT_MS / 1000}
          onClose={closeInstructions}
        />
      )}
    </main>
  )
}
