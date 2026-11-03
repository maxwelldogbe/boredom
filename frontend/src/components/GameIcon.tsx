import type { ReactNode } from 'react'

/** Line drawings per game (inline SVG in the text colour; no emoji, no image files). Solo
 *  challenges use their game's drawing. Unknown ids draw nothing. */
const DRAWINGS: Record<string, ReactNode> = {
  rps: (
    <>
      <circle cx="6" cy="16" r="3.5" />
      <rect x="11" y="4" width="8" height="10" rx="1" />
      <path d="M13 22l6-6M19 22l-6-6" />
    </>
  ),
  guess_race: <path d="M13 2L5 14h6l-1 8 8-12h-6l1-8z" />,
  hangman: (
    <>
      <path d="M4 22h10M7 22V3h9v3" />
      <circle cx="16" cy="9" r="2.5" />
      <path d="M16 11.5V17M13 14h6M16 17l-2.5 3M16 17l2.5 3" />
    </>
  ),
  dots_and_boxes: (
    <>
      <rect x="5" y="5" width="7" height="7" />
      <circle cx="19" cy="5" r="0.8" fill="currentColor" />
      <circle cx="5" cy="19" r="0.8" fill="currentColor" />
      <circle cx="12" cy="19" r="0.8" fill="currentColor" />
      <circle cx="19" cy="12" r="0.8" fill="currentColor" />
      <circle cx="19" cy="19" r="0.8" fill="currentColor" />
    </>
  ),
  liars_dice: (
    <>
      <rect x="4" y="4" width="16" height="16" rx="3" />
      <circle cx="9" cy="9" r="1.2" fill="currentColor" />
      <circle cx="15" cy="15" r="1.2" fill="currentColor" />
      <circle cx="12" cy="12" r="1.2" fill="currentColor" />
    </>
  ),
  name_it: <path d="M4 5h16v11H9l-5 4V5z" />,
  tic_tac_toe: (
    <>
      <path d="M9 3v18M15 3v18M3 9h18M3 15h18" />
      <path d="M4.5 4.5l3 3M7.5 4.5l-3 3" />
      <circle cx="18" cy="18" r="1.6" />
    </>
  ),
  connect_four: (
    <>
      <rect x="3" y="5" width="18" height="15" rx="2" />
      <circle cx="8" cy="10" r="1.6" />
      <circle cx="12" cy="10" r="1.6" />
      <circle cx="16" cy="10" r="1.6" />
      <circle cx="8" cy="15" r="1.6" fill="currentColor" />
      <circle cx="12" cy="15" r="1.6" fill="currentColor" />
      <circle cx="16" cy="15" r="1.6" />
    </>
  ),
  penalty_kick: (
    <>
      <path d="M3 18V6h18v12" />
      <path d="M3 10h18M7 6v12M12 6v12M17 6v12" opacity="0.4" />
      <circle cx="12" cy="20" r="2" fill="currentColor" />
    </>
  ),
  checkers: (
    <>
      <ellipse cx="12" cy="15" rx="7" ry="3" />
      <path d="M5 15v-3M19 15v-3" />
      <ellipse cx="12" cy="12" rx="7" ry="3" />
    </>
  ),
}

export function GameIcon({ id, size = 24 }: { id: string; size?: number }) {
  const drawing = DRAWINGS[id]
  if (!drawing) return null
  return (
    <svg
      className="game-icon"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {drawing}
    </svg>
  )
}
