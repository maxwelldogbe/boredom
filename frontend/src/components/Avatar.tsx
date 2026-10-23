import { useState } from 'react'
import { avatarUrl, isKnownAvatar } from '../lib/avatar'
import type { Avatar as AvatarData } from '../types/protocol'

interface AvatarProps {
  avatar?: AvatarData | null
  nickname: string
  color: string
}

/** DiceBear image on the player's color; falls back to their initial if there is no image. */
export function Avatar({ avatar, nickname, color }: AvatarProps) {
  const [failedUrl, setFailedUrl] = useState<string | null>(null)
  const url = isKnownAvatar(avatar) ? avatarUrl(avatar) : null
  const initial = (nickname.trim()[0] ?? '?').toUpperCase()
  return (
    <span className="chip__avatar" style={{ background: color }} aria-hidden="true">
      {url && failedUrl !== url ? (
        <img src={url} alt="" width={40} height={40} loading="lazy" onError={() => setFailedUrl(url)} />
      ) : (
        <span className="chip__initial">{initial}</span>
      )}
    </span>
  )
}
