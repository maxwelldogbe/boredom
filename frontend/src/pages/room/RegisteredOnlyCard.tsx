import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button } from '../../components/Button'
import { PlayerCards } from '../../components/PlayerCards'
import { friendlyError } from '../../lib/errors'
import { useRoomActions } from '../../state/context'
import type { RoomPublic } from '../../types/protocol'

/** For a guest while the host's game is registered-only (PROTOCOL.md 12). Never names the game.
 *  While it runs (`playing`), the players and a Leave button come with it. */
export function RegisteredOnlyCard({ room, me, playing = false }: { room: RoomPublic; me: string; playing?: boolean }) {
  const navigate = useNavigate()
  const { leaveRoom, toast } = useRoomActions()
  const [busy, setBusy] = useState(false)

  const leave = async () => {
    setBusy(true)
    try {
      await leaveRoom('/', (to) => navigate(to, { replace: true }))
    } catch (err) {
      toast(friendlyError(err), 'error')
      setBusy(false)
    }
  }

  return (
    <section className="card stack registered-only" aria-labelledby="registered-only-title">
      <h2 id="registered-only-title">The host picked a game for registered players.</h2>
      <p>Create a free account to join in.</p>
      <Button block onClick={() => navigate(`/signup?next=${encodeURIComponent(`/room/${room.code}`)}`)}>
        Create account
      </Button>
      {playing && (
        <>
          <PlayerCards
            room={room}
            me={me}
            label="Players in the room"
            entries={room.players.map((player) => ({ id: player.id, notes: player.inGame ? [] : ['waiting'] }))}
          />
          <Button variant="danger" block onClick={leave} disabled={busy}>
            {busy ? 'Leaving…' : 'Leave room'}
          </Button>
        </>
      )}
    </section>
  )
}
