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

/** A random allowed avatar for the shuffle button, never equal to `current`. The server
 *  validates it again and decides whether the change is allowed. */
export function randomAvatar(current?: Avatar): Avatar {
  const bytes = new Uint8Array(5)
  for (;;) {
    crypto.getRandomValues(bytes)
    const style = C.AVATAR_STYLES[bytes[0] % C.AVATAR_STYLES.length]
    const seed = Array.from(bytes.subarray(1), (b) => b.toString(16).padStart(2, '0')).join('')
    if (style !== current?.style || seed !== current?.seed) return { style, seed }
  }
}
