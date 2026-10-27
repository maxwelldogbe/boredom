import { useEffect, useState } from 'react'
import { Button } from '../../components/Button'
import { InviteFriendsButton } from '../../components/Invites'
import { FreeGamesLeft, LockWall } from '../../components/LockWall'
import { Modal } from '../../components/Modal'
import { PlayerCards } from '../../components/PlayerCards'
import { gameUi } from '../../games/registry'
import { hasGameInstructions } from '../../games/instructions'
import { copyText } from '../../lib/clipboard'
import { C } from '../../lib/constants'
import { errorCode, friendlyError } from '../../lib/errors'
import { RequestError } from '../../lib/socket'
import { useRoomActions } from '../../state/context'
import { useGuestQuota } from '../../state/guestQuotaContext'
import { useSocial } from '../../state/socialContext'
import type { RoomPublic } from '../../types/protocol'
import { GamePicker } from './GamePicker'
import { InvitePanel } from './InvitePanel'
import { everyoneReady, notReady, notReadyMessage, readyCheck } from './readyCheck'
import { startBlocker } from './startBlocker'

export function Lobby({ room, me, onHowToPlay = () => {} }: { room: RoomPublic; me: string; onHowToPlay?: () => void }) {
  const { setReady, startGame, toast } = useRoomActions()
  const { signedIn } = useSocial()
  const { refresh, handleError } = useGuestQuota()
  const [starting, setStarting] = useState(false)
  const [readyBusy, setReadyBusy] = useState(false)
  const [confirmStart, setConfirmStart] = useState(false)
  const isHost = room.hostId === me
  const selected = gameUi(room.selectedGame)
  const blocker = startBlocker(room)
  const check = readyCheck(room)
  const allReady = check !== null && everyoneReady(check)
  const waitingFor = check ? notReady(room) : []
  const imReady = room.players.some((p) => p.id === me && p.ready === true)
  const canInvite = signedIn && room.players.some((p) => p.id === me && p.type === 'registered')
  const meLocked = room.players.some((p) => p.id === me && p.locked === true)

  useEffect(() => {
    if (meLocked) refresh()
  }, [meLocked, refresh])

  const start = async () => {
    setConfirmStart(false)
    setStarting(true)
    try {
      await startGame()
    } catch (err) {
      handleError(err)
      const names = err instanceof RequestError ? (err.data?.nicknames as string[] | undefined) : undefined
      toast(
        errorCode(err) === 'GUEST_LIMIT' && names?.length
          ? `${new Intl.ListFormat('en').format(names)} can't play right now. They need an account, or wait until more players join.`
          : friendlyError(err),
        'error',
      )
    } finally {
      setStarting(false)
    }
  }

  // Start is never blocked by the ready check: the host is only asked to confirm.
  const tapStart = () => (waitingFor.length > 0 ? setConfirmStart(true) : start())

  const toggleReady = async () => {
    setReadyBusy(true)
    try {
      await setReady(!imReady)
    } catch (err) {
      toast(friendlyError(err), 'error')
    } finally {
      setReadyBusy(false)
    }
  }

  const notes = (id: string) => {
    const used = room.players.some((p) => p.id === id && p.locked === true) ? ['Games used'] : []
    if (id === room.hostId) return ['👑 Host', ...used]
    return room.players.some((p) => p.id === id && p.ready === true) ? ['✓ Ready', ...used] : used
  }

  return (
    <div className="stack lobby">
      <LockWall />
      <FreeGamesLeft />
      {!isHost && (
        <section className="card stack lobby__next" aria-label="Next game">
          {selected ? (
            <>
              <p>
                Next game: <strong>{selected.name}</strong> {selected.icon}
              </p>
              {check && (
                <Button
                  block
                  variant={imReady ? 'secondary' : 'primary'}
                  className={`lobby__ready${imReady ? ' lobby__ready--on' : ''}`}
                  aria-pressed={imReady}
                  disabled={readyBusy}
                  onClick={toggleReady}
                >
                  {imReady ? 'Ready ✓' : "I'm ready"}
                </Button>
              )}
              {check && imReady && <p className="muted lobby__reason">Tap again if you're not ready after all.</p>}
              {hasGameInstructions(room.selectedGame) && (
                <Button variant="secondary" onClick={onHowToPlay}>
                  How to play
                </Button>
              )}
            </>
          ) : (
            <p className="muted">The host hasn't picked a game yet.</p>
          )}
          <p className="lobby__waiting">⏳ Waiting for the host to start.</p>
        </section>
      )}

      <button
        type="button"
        className="lobby__code"
        onClick={async () => toast((await copyText(room.code)) ? 'Code copied' : room.code)}
        aria-label={`Room code ${room.code.split('').join(' ')}. Tap to copy.`}
      >
        <span className="lobby__code-label">Room code</span>
        <span className="lobby__code-value">{room.code}</span>
        <span className="lobby__code-hint">Tap to copy</span>
      </button>

      {canInvite && <InviteFriendsButton />}

      <InvitePanel code={room.code} />

      <section className="card stack" aria-labelledby="players-title">
        <h2 id="players-title" className="section-title">
          Players ({room.players.length}/{C.MAX_PLAYERS})
        </h2>
        <PlayerCards
          room={room}
          me={me}
          entries={room.players.map((p) => ({ id: p.id, notes: notes(p.id) }))}
        />
      </section>

      {isHost && (
        <>
          <GamePicker room={room} onHowToPlay={onHowToPlay} />
          <div className="lobby__start">
            {check && (
              <p className={`lobby__ready-count${allReady ? ' lobby__ready-count--all' : ''}`} role="status">
                {allReady && check.total > 0 ? '✓ ' : ''}
                {check.count} of {check.total} ready
              </p>
            )}
            <Button
              block
              className={allReady && check.total > 0 ? 'lobby__start-btn--all-ready' : undefined}
              onClick={tapStart}
              disabled={Boolean(blocker) || starting}
            >
              {starting ? 'Starting…' : 'Start game'}
            </Button>
            {blocker && <p className="muted lobby__reason">{blocker}</p>}
          </div>
        </>
      )}

      {confirmStart && (
        <Modal
          title="Start without everyone?"
          onClose={() => setConfirmStart(false)}
          actions={
            <>
              <Button block onClick={() => setConfirmStart(false)}>
                Wait
              </Button>
              <Button variant="secondary" block onClick={start}>
                Start anyway
              </Button>
            </>
          }
        >
          <p>{notReadyMessage(waitingFor)}</p>
        </Modal>
      )}
    </div>
  )
}
