import { useState } from 'react'
import { Button } from '../../components/Button'
import { Modal } from '../../components/Modal'
import { friendlyError } from '../../lib/errors'
import { useRoomActions } from '../../state/context'
import type { RoomPublic } from '../../types/protocol'

interface TopBarProps {
  room: RoomPublic
  me: string
  onLeaving: () => void
  onLeft: () => void
}

/** Room code, your session score and Leave (with confirmation). */
export function TopBar({ room, me, onLeaving, onLeft }: TopBarProps) {
  const { leaveRoom, toast } = useRoomActions()
  const [confirm, setConfirm] = useState(false)
  const [busy, setBusy] = useState(false)
  const playing = room.status === 'playing'

  const leave = async () => {
    setBusy(true)
    onLeaving()
    try {
      await leaveRoom()
      onLeft()
    } catch (err) {
      toast(friendlyError(err), 'error')
      setBusy(false)
    }
  }

  return (
    <header className="topbar">
      <span className="topbar__code" aria-label={`Room ${room.code}`}>
        🏠 {room.code}
      </span>
      <span className="topbar__score">Score: {room.scoreboard[me] ?? 0}</span>
      <Button variant="ghost" onClick={() => setConfirm(true)}>
        Leave
      </Button>
      {confirm && (
        <Modal
          title="Leave this room?"
          onClose={() => setConfirm(false)}
          actions={
            <>
              <Button variant="danger" block onClick={leave} disabled={busy}>
                {busy ? 'Leaving…' : 'Leave room'}
              </Button>
              <Button variant="secondary" block onClick={() => setConfirm(false)} disabled={busy}>
                Stay
              </Button>
            </>
          }
        >
          <p>
            {playing
              ? "A game is running. If you leave, you can't come back into this game."
              : 'You can join again later with the room code.'}
          </p>
        </Modal>
      )}
    </header>
  )
}
