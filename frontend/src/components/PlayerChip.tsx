import type { Player } from '../types/protocol'

interface PlayerChipProps {
  player: Pick<Player, 'nickname' | 'emoji' | 'color'> & { online?: boolean }
  isHost?: boolean
  isMe?: boolean
  size?: 'sm' | 'md'
  extra?: string
}

/** Avatar (emoji on the player's color) + nickname, with host, you and offline labels. */
export function PlayerChip({ player, isHost, isMe, size = 'md', extra }: PlayerChipProps) {
  const offline = player.online === false
  return (
    <span className={`chip chip--${size}${offline ? ' chip--offline' : ''}`}>
      <span className="chip__avatar" style={{ background: player.color }} aria-hidden="true">
        {player.emoji}
      </span>
      <span className="chip__name">
        {player.nickname}
        {isMe && <span className="chip__tag"> (you)</span>}
      </span>
      {isHost && (
        <span className="chip__host" title="Host">
          <span aria-hidden="true">👑</span>
          <span className="visually-hidden">host</span>
        </span>
      )}
      {offline && <span className="chip__tag">offline</span>}
      {extra && <span className="chip__extra">{extra}</span>}
    </span>
  )
}
