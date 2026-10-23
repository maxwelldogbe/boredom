import { useState } from 'react'
import { Button } from '../../components/Button'
import { PlayerChip } from '../../components/PlayerChip'
import { gameUi } from '../../games/registry'
import { friendlyError } from '../../lib/errors'
import { formatPoints } from '../../lib/format'
import { playerById } from '../../lib/players'
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
          <ol className="rank-list">
            {[...lastResults]
              .sort((a, b) => a.placement - b.placement)
              .map((r) => (
                <li key={r.playerId} className={r.playerId === me ? 'rank-list__me' : undefined}>
                  <span className="rank-list__place">
                    <span aria-hidden="true">{MEDALS[r.placement] ?? ''} </span>
                    {ordinal(r.placement)}
                  </span>
                  <PlayerChip player={playerById(room, r.playerId)} isMe={r.playerId === me} size="sm" />
                  <span className="rank-list__points">
                    <span className="muted rank-list__score">score {formatPoints(r.score)} · </span>+{formatPoints(r.points)}
                  </span>
                </li>
              ))}
          </ol>
        </section>
      )}

      <section className="card stack" aria-labelledby="session-title">
        <h2 id="session-title" className="section-title">
          Session scoreboard
        </h2>
        <ol className="rank-list">
          {session.map((p) => {
            const points = room.scoreboard[p.id] ?? 0
            const leader = topScore > 0 && points === topScore
            const wins = room.wins[p.id] ?? 0
            return (
              <li key={p.id} className={leader ? 'rank-list__leader' : undefined}>
                <PlayerChip player={p} isMe={p.id === me} size="sm" extra={wins ? `${wins} win${wins > 1 ? 's' : ''}` : undefined} />
                <span className="rank-list__points">
                  {leader && <span title="Session leader">👑 </span>}
                  {formatPoints(points)}
                </span>
              </li>
            )
          })}
        </ol>
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
