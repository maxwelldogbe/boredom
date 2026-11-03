import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { friendlyError } from '../lib/errors'
import { getRoomToken, setRoomToken } from '../lib/roomTokens'
import { useRoomActions } from '../state/context'
import { resumePayload } from '../state/useResume'
import { Button } from './Button'
import { Modal } from './Modal'

/** ALREADY_IN_GAME (PROTOCOL.md 6.3): back to that game, or leave it (a forfeit). */
export function AlreadyInGameDialog({ code, onClose }: { code: string; onClose: () => void }) {
  const navigate = useNavigate()
  const { socket, joinRoom, leaveRoom, toast } = useRoomActions()
  const [busy, setBusy] = useState(false)

  /** The seat's roomToken: stored here, or from the server for an account. */
  const ensureToken = async () => {
    if (getRoomToken(code)) return
    const payload = resumePayload()
    const seat = payload ? (await socket.request('room:resume', payload)).resume : null
    if (seat?.code === code) setRoomToken(code, seat.roomToken)
  }

  const back = async () => {
    setBusy(true)
    try {
      await ensureToken()
      navigate(`/room/${code}`)
    } catch (err) {
      toast(friendlyError(err, code), 'error')
      setBusy(false)
    }
  }

  const leave = async () => {
    setBusy(true)
    try {
      await ensureToken()
      await joinRoom(code)
      await leaveRoom('/')
      onClose()
    } catch (err) {
      toast(friendlyError(err, code), 'error')
      setBusy(false)
    }
  }

  return (
    <Modal
      title={`You're still in a game in room ${code}.`}
      onClose={() => !busy && onClose()}
      actions={
        <>
          <Button block onClick={() => void back()} disabled={busy} data-autofocus>
            Return to game
          </Button>
          <Button variant="danger" block onClick={() => void leave()} disabled={busy}>
            Leave it
          </Button>
        </>
      }
    >
      <p>Leaving counts as a forfeit in that game.</p>
    </Modal>
  )
}
