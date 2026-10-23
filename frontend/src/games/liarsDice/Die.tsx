// Pip cells (0-8, row by row in a 3x3 grid) for each face.
const PIPS: Record<number, number[]> = {
  1: [4],
  2: [0, 8],
  3: [0, 4, 8],
  4: [0, 2, 6, 8],
  5: [0, 2, 4, 6, 8],
  6: [0, 2, 3, 5, 6, 8],
}

interface DieProps {
  face: number
  size?: 'lg' | 'sm'
  highlight?: boolean
}

/** A CSS die face. Screen readers get the number. */
export function Die({ face, size = 'lg', highlight = false }: DieProps) {
  return (
    <span className={`die die--${size}${highlight ? ' die--hit' : ''}`} role="img" aria-label={`${face}`}>
      {Array.from({ length: 9 }, (_, i) => (
        <span key={i} className={PIPS[face]?.includes(i) ? 'die__pip' : 'die__blank'} />
      ))}
    </span>
  )
}

/** A face-down die (an opponent's hidden die). */
export function HiddenDie() {
  return <span className="die die--sm die--hidden" aria-hidden="true" />
}
