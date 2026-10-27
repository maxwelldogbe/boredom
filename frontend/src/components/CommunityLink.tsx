import { communityUrl } from '../config/community'

const LABEL = 'Join our WhatsApp community'

/** WhatsApp-style speech bubble with a phone (drawn here, no icon library). */
function WhatsAppIcon() {
  return (
    <svg className="community__icon" viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" focusable="false">
      <path
        fill="currentColor"
        d="M12 2a10 10 0 0 0-8.6 15.1L2 22l5-1.3A10 10 0 1 0 12 2Zm0 18.2a8.2 8.2 0 0 1-4.2-1.2l-.3-.2-3 .8.8-2.9-.2-.3A8.2 8.2 0 1 1 12 20.2Zm4.5-6.1c-.2-.1-1.5-.7-1.7-.8s-.4-.1-.6.1-.6.8-.8 1-.3.2-.5.1a6.7 6.7 0 0 1-3.3-2.9c-.3-.4.3-.4.7-1.3.1-.2 0-.3 0-.4l-.8-1.8c-.2-.5-.4-.4-.6-.4h-.5a1 1 0 0 0-.7.3 3 3 0 0 0-.9 2.2 5.2 5.2 0 0 0 1.1 2.7 11.8 11.8 0 0 0 4.5 4c1.7.7 2.3.8 3.2.6a2.7 2.7 0 0 0 1.8-1.2 2.2 2.2 0 0 0 .1-1.3c0-.1-.2-.2-.5-.3Z"
      />
    </svg>
  )
}

interface CommunityLinkProps {
  /** "button": a full-width secondary button; "small": a compact one; "menu": a menu row. */
  variant?: 'button' | 'small' | 'menu'
  /** Show "Share your experience and meet other players." under it. */
  note?: boolean
  onClick?: () => void
}

/** "Join our WhatsApp community": always a new tab, so it can never take a player out of a
 *  room. Nothing about the player is added to the link. Renders nothing if the link is unusable. */
export function CommunityLink({ variant = 'button', note = false, onClick }: CommunityLinkProps) {
  const href = communityUrl()
  if (!href) return null
  const className =
    variant === 'menu'
      ? 'community community--menu'
      : `btn btn--secondary community${variant === 'button' ? ' btn--block' : ' community--small'}`
  const link = (
    <a
      className={className}
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      aria-label={`${LABEL} (opens in a new tab)`}
      onClick={onClick}
    >
      <WhatsAppIcon />
      {LABEL}
    </a>
  )
  if (!note) return link
  return (
    <div className="community-block">
      {link}
      <p className="muted community__note">Share your experience and meet other players.</p>
    </div>
  )
}

