/** DiceBear image URL for a server-assigned avatar (the server only sends {style, seed}). */
import type { Avatar } from '../types/protocol'
import { C } from './constants'

export function avatarUrl(avatar: Avatar): string {
  const style = encodeURIComponent(avatar.style)
  const seed = encodeURIComponent(avatar.seed)
  return `https://api.dicebear.com/${C.AVATAR_API_VERSION}/${style}/svg?seed=${seed}`
}

/** True only for avatars the shared constants allow (never build URLs from anything else). */
export function isKnownAvatar(avatar: Avatar | null | undefined): avatar is Avatar {
  return (
    !!avatar &&
    C.AVATAR_STYLES.includes(avatar.style) &&
    new RegExp(C.AVATAR_SEED_PATTERN).test(avatar.seed)
  )
}
