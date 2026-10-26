import { useState } from 'react'
import { Button } from '../../components/Button'
import { PlayerChip } from '../../components/PlayerChip'
import { gameUi } from '../../games/registry'
import { hasGameInstructions } from '../../games/instructions'
import { copyText } from '../../lib/clipboard'
import { C } from '../../lib/constants'
import { friendlyError } from '../../lib/errors'
import { useRoomActions } from '../../state/context'
import type { RoomPublic } from '../../types/protocol'
import { GamePicker } from './GamePicker'
import { InvitePanel } from './InvitePanel'
import { startBlocker } from './startBlocker'

export function Lobby({ room, me, onHowToPlay = () => {} }: { room: RoomPublic; me: string; onHowToPlay?: () => void }) {
  const { startGame, toast } = useRoomActions()
  const [starting, setStarting] = useState(false)
  const isHost = room.hostId === me
  const selected = gameUi(room.selectedGame)
  const blocker = startBlocker(room)

  const start = async () => {
    setStarting(true)
    try {
      await startGame()
    } catch (err) {
      toast(friendlyError(err), 'error')
    } finally {
      setStarting(false)
    }
  }

  return (
    <div className="stack lobby">
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

      <InvitePanel code={room.code} />

      <section className="card stack" aria-labelledby="players-title">
        <h2 id="players-title" className="section-title">
          Players ({room.players.length}/{C.MAX_PLAYERS})
        </h2>
        <ul className="player-list">
          {room.players.map((p) => (
            <li key={p.id}>
              <PlayerChip player={p} isHost={p.id === room.hostId} isMe={p.id === me} />
            </li>
          ))}
        </ul>
      </section>

      {isHost ? (
        <>
          <GamePicker room={room} onHowToPlay={onHowToPlay} />
          <div className="lobby__start">
            <Button block onClick={start} disabled={Boolean(blocker) || starting}>
              {starting ? 'Starting…' : 'Start game'}
            </Button>
            {blocker && <p className="muted lobby__reason">{blocker}</p>}
          </div>
        </>
      ) : (
        <section className="card stack">
          {selected ? (
            <>
              <p>
                Next game: <strong>{selected.name}</strong> {selected.icon}
              </p>
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
    </div>
  )
}
