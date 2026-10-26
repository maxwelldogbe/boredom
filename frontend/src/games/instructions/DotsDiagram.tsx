import { DOTS_PALETTE } from '../dotsAndBoxes/palette'

export function DotsDiagram() {
  return (
    <div className="how-to-play__visual">
      <svg role="img" aria-label="Three sides of a box are drawn. Draw this line to claim the box." viewBox="0 0 220 130">
        <rect x="55" y="20" width="90" height="90" fill="none" stroke={DOTS_PALETTE[0]} strokeWidth="7" strokeLinecap="round" />
        <line x1="55" y1="110" x2="145" y2="110" stroke={DOTS_PALETTE[0]} strokeWidth="7" strokeLinecap="round" strokeDasharray="8 8" />
        <text x="110" y="125" textAnchor="middle" fill="white" fontSize="11">Draw this line to claim the box!</text>
      </svg>
    </div>
  )
}
