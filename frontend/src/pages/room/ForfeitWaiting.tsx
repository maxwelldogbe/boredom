import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button } from '../../components/Button'
import { PlayerCards } from '../../components/PlayerCards'
import { friendlyError } from '../../lib/errors'
import { useRoomActions } from '../../state/context'
import type { RoomPublic } from '../../types/protocol'

export function ForfeitWaiting({ room, me }: { room: RoomPublic; me: string }) {
  const navigate = useNavigate()
  const { leaveRoom, toast } = useRoomActions()
  const [busy, setBusy] = useState(false)

  const leave = async () => {
    setBusy(true)
    try {
      await leaveRoom()
      navigate('/', { replace: true })
    } catch (err) {
      toast(friendlyError(err), 'error')
      setBusy(false)
    }
  }

  return (
    <section className="card stack forfeit-waiting" aria-labelledby="forfeit-waiting-title">
      <h1 id="forfeit-waiting-title">You forfeited the game</h1>
      <p>You forfeited the game. The others are still playing. You'll return to the room when it ends.</p>
      <PlayerCards
        room={room}
        me={me}
        label="Players still in the room"
        entries={room.players.map((player) => ({
          id: player.id,
          notes: player.inGame ? [] : ['forfeited'],
        }))}
      />
      <Button variant="danger" block onClick={leave} disabled={busy}>
        {busy ? 'Leaving…' : 'Leave room'}
      </Button>
    </section>
  )
}
