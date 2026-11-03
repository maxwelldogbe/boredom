import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button } from '../../components/Button'
import { ConnectionBanner, OnlineOnly } from '../../components/ConnectionBanner'
import { HowToPlayModal } from '../../components/HowToPlayModal'
import { Logo } from '../../components/Logo'
import { Modal } from '../../components/Modal'
import { gameInstructions } from '../../games/instructions'
import { CHALLENGE_INSTRUCTIONS, isChallenge } from '../../games/solo/instructions'
import { ChallengeScreen } from '../../games/solo/ChallengeScreen'
import { ChallengeEnd } from '../../games/solo/ChallengeEnd'
import { DOTS_GAME, soloSettings } from '../../games/soloGames'
import { C } from '../../lib/constants'
import { friendlyError } from '../../lib/errors'
import { nameOf } from '../../lib/players'
import { difficultyLabel, withBotLine } from '../../lib/solo'
import { useRoomActions, useRoomState } from '../../state/context'
import type { RoomPublic, SoloResult } from '../../types/protocol'
import { GameScreen } from './GameScreen'

const BANNERS: Record<SoloResult['outcome'], string> = { win: 'You win!', lose: 'You lose', draw: 'Draw' }

/** A solo room (PROTOCOL.md 16): the game against the bot, with no room code, series,
 *  reactions or ready check; Quit instead of Forfeit and Leave. */
export function SoloRoom({ room, me }: { room: RoomPublic; me: string }) {
  const navigate = useNavigate()
  const { soloQuit, toast } = useRoomActions()
  const [howTo, setHowTo] = useState(false)
  const [confirm, setConfirm] = useState(false)
  const [busy, setBusy] = useState(false)
  const difficulty = room.soloVariant?.difficulty ?? 'medium'
  const size = room.soloVariant?.size ?? 5
  const challenge = isChallenge(room.selectedGame)
  const challengeText = room.selectedGame ? CHALLENGE_INSTRUCTIONS[room.selectedGame] : undefined
  const content = challengeText
    ? challengeText()
    : room.selectedGame
      ? withBotLine(
          gameInstructions(room.selectedGame, { settings: soloSettings(room.selectedGame, size), constants: C, playerCount: 2 })!,
          difficulty,
          room.selectedGame,
        )
      : null

  const quit = async (to: string) => {
    setBusy(true)
    try {
      await soloQuit(to, (dest) => navigate(dest, { replace: true }))
    } catch (err) {
      toast(friendlyError(err), 'error')
      setBusy(false)
    }
  }

  return (
    <main className="page room solo-room">
      <header className="topbar">
        <span className="topbar__brand">
          <Logo variant="mark" size={28} />
        </span>
        {content && (
          <Button variant="ghost" onClick={() => setHowTo(true)}>
            How to play
          </Button>
        )}
        {room.status === 'playing' && (
          <Button variant="secondary" onClick={() => setConfirm(true)}>
            Quit
          </Button>
        )}
      </header>
      <ConnectionBanner />
      <OnlineOnly>
      {challenge ? <ChallengeScreen /> : <GameScreen room={room} me={me} />}
      {room.status === 'finished' &&
        (challenge ? (
          <ChallengeEnd busy={busy} onQuit={quit} />
        ) : (
          <SoloEnd room={room} me={me} difficulty={difficulty} busy={busy} onQuit={quit} />
        ))}
      </OnlineOnly>
      {confirm && room.status === 'playing' && (
        <Modal
          title={challenge ? 'Quit this run? Your score is not saved.' : 'Quit this game? Nothing is lost.'}
          onClose={() => !busy && setConfirm(false)}
          actions={
            <>
              <Button variant="danger" block onClick={() => void quit('/solo')} disabled={busy}>
                {busy ? 'Quitting…' : 'Quit'}
              </Button>
              <Button variant="secondary" block onClick={() => setConfirm(false)} disabled={busy} data-autofocus>
                Keep playing
              </Button>
            </>
          }
        >
          {null}
        </Modal>
      )}
      {howTo && content && (
        <HowToPlayModal
          content={content}
          inGame={room.status === 'playing'}
          roundsToWin={1}
          onClose={() => setHowTo(false)}
        />
      )}
    </main>
  )
}

function SoloEnd({
  room,
  me,
  difficulty,
  busy,
  onQuit,
}: {
  room: RoomPublic
  me: string
  difficulty: string
  busy: boolean
  onQuit: (to: string) => Promise<void>
}) {
  const gameId = room.selectedGame
  const { game } = useRoomState()
  const dots = game?.gameId === 'dots_and_boxes' ? game.view : null
  const size = room.soloVariant?.size
  const { soloAgain, toast } = useRoomActions()
  const result = game && 'soloResult' in game.view ? (game.view.soloResult ?? null) : null
  if (!result) return null
  const record = result.record
  const again = async () => {
    try {
      await soloAgain()
    } catch (err) {
      toast(friendlyError(err), 'error')
    }
  }
  return (
    <section className="card stack solo-end" aria-labelledby="solo-end-title">
      <h2 id="solo-end-title" className={`solo-end__banner solo-end__banner--${result.outcome}`} aria-live="polite">
        {BANNERS[result.outcome]}
      </h2>
      {dots && (
        <p>
          Boxes:{' '}
          {dots.order.map((id) => `${nameOf(room, id, me)} ${dots.scores[id] ?? 0}`).join(', ')}
        </p>
      )}
      {result.brag && (
        <p className="solo-end__brag" role="status">
          {result.brag.awarded > 0
            ? `+${result.brag.awarded} Brag coins (you have ${result.brag.balance})`
            : `You hit today's limit of ${result.brag.dailyCap} Brag coins from bots. Come back tomorrow!`}
        </p>
      )}
      {record && (
        <p>
          Your record on {size ? `${size}x${size} ` : ''}{difficultyLabel(difficulty)}: played {record.plays}, won {record.wins}, lost {record.losses},
          drew {record.draws}
        </p>
      )}
      <Button block onClick={() => void again()} disabled={busy}>
        Play again
      </Button>
      <Button variant="secondary" block onClick={() => void onQuit(`/solo?game=${gameId ?? ''}`)} disabled={busy}>
        {gameId === DOTS_GAME ? 'Change difficulty or size' : 'Change difficulty'}
      </Button>
      <Button variant="ghost" block onClick={() => void onQuit('/solo')} disabled={busy}>
        Back
      </Button>
    </section>
  )
}
