import { useState } from 'react'
import { Button } from '../../components/Button'
import { Logo } from '../../components/Logo'
import { Modal } from '../../components/Modal'
import { ReactionButton } from '../../components/Reactions'
import { hasGameInstructions } from '../../games/instructions'
import { friendlyError } from '../../lib/errors'
import { formatPoints } from '../../lib/format'
import { setReactionsHidden, useReactionsHidden } from '../../lib/reactionsPref'
import { useRoomActions } from '../../state/context'
import type { RoomPublic } from '../../types/protocol'

interface TopBarProps {
  room: RoomPublic
  me: string
  onLeaving: () => void
  onLeft: () => void
  onHowToPlay?: () => void
}

/** Room code, your session score and Leave (with confirmation). */
export function TopBar({ room, me, onLeaving, onLeft, onHowToPlay = () => {} }: TopBarProps) {
  const { leaveRoom, quitGame, toast } = useRoomActions()
  const [confirm, setConfirm] = useState(false)
  const [forfeitConfirm, setForfeitConfirm] = useState(false)
  const [forfeitBusy, setForfeitBusy] = useState(false)
  const [busy, setBusy] = useState(false)
  const [menuOpen, setMenuOpen] = useState(false)
  const reactionsOff = useReactionsHidden()
  const playing = room.status === 'playing'
  const stillPlaying = room.players.some((player) => player.id === me && player.inGame)
  const activeOpponents = room.players.filter((player) => player.inGame && player.id !== me)

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
      <span className="topbar__brand">
        <Logo variant="mark" size={28} />
        <span className="topbar__code" aria-label={`Room ${room.code}`}>
          {room.code}
        </span>
      </span>
      <span className="topbar__score">Score: {formatPoints(room.scoreboard[me] ?? 0)}</span>
      <ReactionButton />
      <div className="topbar__menu">
        <Button variant="ghost" aria-expanded={menuOpen} onClick={() => setMenuOpen((open) => !open)}>
          Menu
        </Button>
        {menuOpen && (
          <div className="topbar__menu-panel">
            {hasGameInstructions(room.selectedGame) && (
              <button
                type="button"
                onClick={() => {
                  setMenuOpen(false)
                  onHowToPlay()
                }}
              >
                How to play
              </button>
            )}
            <button type="button" aria-pressed={reactionsOff} onClick={() => setReactionsHidden(!reactionsOff)}>
              {reactionsOff ? '✓ ' : ''}Hide reactions
            </button>
          </div>
        )}
      </div>
      {playing && stillPlaying && (
        <Button variant="secondary" className="topbar__forfeit" onClick={() => setForfeitConfirm(true)}>
          🏳️ Forfeit
        </Button>
      )}
      <Button variant="ghost" onClick={() => setConfirm(true)}>
        Leave
      </Button>
      {forfeitConfirm && playing && stillPlaying && (
        <Modal
          title="Forfeit this game?"
          onClose={() => !forfeitBusy && setForfeitConfirm(false)}
          actions={
            <>
              <Button variant="primary" block onClick={() => setForfeitConfirm(false)} disabled={forfeitBusy}>
                Keep playing
              </Button>
              <Button
                variant="danger"
                block
                disabled={forfeitBusy}
                onClick={async () => {
                  setForfeitBusy(true)
                  try {
                    await quitGame()
                    setForfeitConfirm(false)
                  } catch (err) {
                    toast(friendlyError(err), 'error')
                  } finally {
                    setForfeitBusy(false)
                  }
                }}
              >
                {forfeitBusy ? 'Forfeiting…' : 'Forfeit'}
              </Button>
            </>
          }
        >
          <p>
            {activeOpponents.length === 1 && room.players.filter((player) => player.inGame).length === 2
              ? `${activeOpponents[0].nickname} will win the game. You'll wait in the room.`
              : "You'll be ranked last and wait in the room until the game ends. The others keep playing."}
          </p>
        </Modal>
      )}
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
