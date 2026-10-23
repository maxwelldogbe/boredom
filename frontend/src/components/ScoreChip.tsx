import { formatPoints } from '../lib/format'

interface ScoreChipProps {
  label: string
  score: number
  highlight?: boolean
}

export function ScoreChip({ label, score, highlight }: ScoreChipProps) {
  return (
    <span className={`score-chip${highlight ? ' score-chip--me' : ''}`}>
      <span className="score-chip__label">{label}</span>
      <strong className="score-chip__value">{formatPoints(score)}</strong>
    </span>
  )
}
