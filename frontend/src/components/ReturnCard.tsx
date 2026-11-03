import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { friendlyError } from '../lib/errors'
import { setRoomToken } from '../lib/roomTokens'
import { useRoomActions } from '../state/context'
import type { ResumeSeat } from '../types/protocol'
import { Button } from './Button'
import { Modal } from './Modal'

/** "You're still in room ABCD": back into the seat the server kept, or leave it (two steps). */
export function ReturnCard({ seat, onLeft }: { seat: ResumeSeat; onLeft: () => void }) {
  const navigate = useNavigate()
  const { joinRoom, leaveRoom, toast } = useRoomActions()
  const [busy, setBusy] = useState(false)
  const [confirm, setConfirm] = useState(false)

  const back = async () => {
    setBusy(true)
    try {
      setRoomToken(seat.code, seat.roomToken)
      await joinRoom(seat.code)
      navigate(`/room/${seat.code}`)
    } catch (err) {
      toast(friendlyError(err, seat.code), 'error')
      setBusy(false)
    }
  }

  const leave = async () => {
    setBusy(true)
    try {
      setRoomToken(seat.code, seat.roomToken)
      await joinRoom(seat.code)
      await leaveRoom('/')
      setConfirm(false)
      onLeft()
    } catch (err) {
      toast(friendlyError(err, seat.code), 'error')
    } finally {
      setBusy(false)
    }
  }

  const people = `${seat.playerCount} ${seat.playerCount === 1 ? 'player' : 'players'}`
  return (
    <section className="card stack return-card" aria-labelledby="return-card-title">
      <h2 id="return-card-title" className="return-card__title">
        You're still in room {seat.code}
      </h2>
      <p className="muted">
        {seat.hostNickname ? `${seat.hostNickname}'s room · ` : ''}
        {people}
      </p>
      <Button block onClick={() => void back()} disabled={busy}>
        Return to room
      </Button>
      <button type="button" className="text-button" onClick={() => setConfirm(true)} disabled={busy}>
        Leave room
      </button>
      {confirm && (
        <Modal
          title="Leave this room?"
          onClose={() => !busy && setConfirm(false)}
          actions={
            <>
              <Button variant="danger" block onClick={() => void leave()} disabled={busy}>
                {busy ? 'Leaving…' : 'Leave room'}
              </Button>
              <Button variant="secondary" block onClick={() => setConfirm(false)} disabled={busy}>
                Stay
              </Button>
            </>
          }
        >
          <p>
            {seat.status === 'playing'
              ? 'A game is running. If you leave, you forfeit it.'
              : 'You can join again later with the room code.'}
          </p>
        </Modal>
      )}
    </section>
  )
}
