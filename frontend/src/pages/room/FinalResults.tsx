import { useState } from 'react'
import { Button } from '../../components/Button'
import { PlayerCards } from '../../components/PlayerCards'
import { gameUi } from '../../games/registry'
import { friendlyError } from '../../lib/errors'
import { formatPoints } from '../../lib/format'
import { useRoomActions, useRoomState } from '../../state/context'
import type { RoomPublic } from '../../types/protocol'

const MEDALS: Record<number, string> = { 1: '🥇', 2: '🥈', 3: '🥉' }

function ordinal(n: number): string {
  const suffix = n % 10 === 1 && n % 100 !== 11 ? 'st' : n % 10 === 2 && n % 100 !== 12 ? 'nd' : n % 10 === 3 && n % 100 !== 13 ? 'rd' : 'th'
  return `${n}${suffix}`
}

/** Game results, the session scoreboard with its leader, and host controls. */
export function FinalResults({ room, me }: { room: RoomPublic; me: string }) {
  const { lastResults } = useRoomState()
  const { playAgain, startGame, toast } = useRoomActions()
  const [busy, setBusy] = useState(false)
  const isHost = room.hostId === me
  const game = gameUi(room.selectedGame)

  const session = [...room.players].sort(
    (a, b) => (room.scoreboard[b.id] ?? 0) - (room.scoreboard[a.id] ?? 0),
  )
  const topScore = room.scoreboard[session[0]?.id] ?? 0

  const run = async (again: boolean) => {
    setBusy(true)
    try {
      await playAgain()
      if (again) await startGame()
    } catch (err) {
      toast(friendlyError(err), 'error')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="stack results">
      <h1>Game over</h1>
      {lastResults && (
        <section className="card stack" aria-labelledby="results-title">
          <h2 id="results-title" className="section-title">
            {game?.name ?? 'Results'}
          </h2>
          <PlayerCards
            room={room}
            me={me}
            label="Game results"
            entries={[...lastResults]
              .sort((a, b) => a.placement - b.placement)
              .map((r) => ({
                id: r.playerId,
                value: `+${formatPoints(r.points)}`,
                notes: [`${MEDALS[r.placement] ? `${MEDALS[r.placement]} ` : ''}${ordinal(r.placement)}`, `score ${formatPoints(r.score)}`],
              }))}
          />
        </section>
      )}

      <section className="card stack" aria-labelledby="session-title">
        <h2 id="session-title" className="section-title">
          Session scoreboard
        </h2>
        <PlayerCards
          room={room}
          me={me}
          label="Session scoreboard"
          entries={session.map((p) => {
            const points = room.scoreboard[p.id] ?? 0
            const wins = room.wins[p.id] ?? 0
            const notes = []
            if (topScore > 0 && points === topScore) notes.push(<span title="Session leader">👑 leader</span>)
            if (wins) notes.push(`${wins} win${wins > 1 ? 's' : ''}`)
            return { id: p.id, value: formatPoints(points), notes }
          })}
        />
      </section>

      {isHost ? (
        <div className="stack">
          <Button block onClick={() => run(true)} disabled={busy}>
            Play again
          </Button>
          <Button variant="secondary" block onClick={() => run(false)} disabled={busy}>
            Back to lobby
          </Button>
        </div>
      ) : (
        <p className="lobby__waiting">⏳ Waiting for the host to play again or return to the lobby.</p>
      )}
    </div>
  )
}
