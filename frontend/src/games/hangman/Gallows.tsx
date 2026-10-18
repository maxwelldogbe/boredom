/** Inline SVG gallows; draws one body part per wrong guess (6 parts). */
export function Gallows({ wrongCount, maxWrong }: { wrongCount: number; maxWrong: number }) {
  const parts = [
    <circle key="head" cx="140" cy="62" r="18" />,
    <line key="body" x1="140" y1="80" x2="140" y2="136" />,
    <line key="larm" x1="140" y1="96" x2="116" y2="118" />,
    <line key="rarm" x1="140" y1="96" x2="164" y2="118" />,
    <line key="lleg" x1="140" y1="136" x2="118" y2="168" />,
    <line key="rleg" x1="140" y1="136" x2="162" y2="168" />,
  ]
  const shown = Math.round((Math.min(wrongCount, maxWrong) / maxWrong) * parts.length)
  return (
    <svg
      className="gallows"
      viewBox="0 0 200 200"
      role="img"
      aria-label={`${wrongCount} of ${maxWrong} wrong guesses`}
    >
      <g className="gallows__frame">
        <line x1="20" y1="190" x2="120" y2="190" />
        <line x1="50" y1="190" x2="50" y2="14" />
        <line x1="50" y1="14" x2="140" y2="14" />
        <line x1="140" y1="14" x2="140" y2="44" />
      </g>
      <g className="gallows__body">{parts.slice(0, shown)}</g>
    </svg>
  )
}
