import type { Player } from '../types/protocol'
import { Avatar } from './Avatar'

interface PlayerChipProps {
  player: Pick<Player, 'nickname' | 'color'> & { avatar?: Player['avatar'] | null; online?: boolean }
  isHost?: boolean
  isMe?: boolean
  size?: 'sm' | 'md'
  extra?: string
}

/** Avatar (DiceBear image on the player's color) + nickname, with host, you and offline labels. */
export function PlayerChip({ player, isHost, isMe, size = 'md', extra }: PlayerChipProps) {
  const offline = player.online === false
  return (
    <span className={`chip chip--${size}${offline ? ' chip--offline' : ''}`}>
      <Avatar avatar={player.avatar} nickname={player.nickname} color={player.color} />
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
