/** The solo bot's face: a small robot drawn inline (no image files, no DiceBear). */
export function BotIcon({ size = 40 }: { size?: number }) {
  return (
    <svg className="bot-icon" width={size} height={size} viewBox="0 0 40 40" aria-hidden="true" focusable="false">
      <line x1="20" y1="4" x2="20" y2="10" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
      <circle cx="20" cy="4" r="2.5" fill="currentColor" />
      <rect x="7" y="10" width="26" height="22" rx="6" fill="none" stroke="currentColor" strokeWidth="2.5" />
      <circle cx="15" cy="20" r="3" fill="currentColor" />
      <circle cx="25" cy="20" r="3" fill="currentColor" />
      <line x1="14" y1="27" x2="26" y2="27" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
      <line x1="4" y1="18" x2="7" y2="18" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
      <line x1="33" y1="18" x2="36" y2="18" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
    </svg>
  )
}
