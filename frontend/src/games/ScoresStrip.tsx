import { ScoreChip } from '../components/ScoreChip'
import { playerById } from '../lib/players'
import type { RoomPublic } from '../types/protocol'

/** Compact score chips for a game, highest first, your chip outlined. */
export function ScoresStrip({ scores, room, me }: { scores: Record<string, number>; room: RoomPublic; me: string }) {
  const ids = Object.keys(scores).sort((a, b) => scores[b] - scores[a])
  return (
    <div className="scores-strip" aria-label="Scores">
      {ids.map((id) => {
        const p = playerById(room, id)
        return <ScoreChip key={id} label={id === me ? 'You' : `${p.emoji} ${p.nickname}`} score={scores[id]} highlight={id === me} />
      })}
    </div>
  )
}
