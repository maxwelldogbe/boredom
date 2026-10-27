import { useEffect, useRef, useState } from 'react'
import { C } from '../lib/constants'
import { errorCode, friendlyError } from '../lib/errors'
import { useReactionsHidden } from '../lib/reactionsPref'
import { useRoomActions, useRoomState } from '../state/context'
import type { ReactionPush, RoomPublic } from '../types/protocol'
import { Avatar } from './Avatar'

/** Spoken names for the REACTION_EMOJIS buttons. */
const EMOJI_NAMES: Record<string, string> = {
  '👏': 'clapping',
  '😂': 'laughing',
  '😮': 'surprised',
  '🔥': 'fire',
  '😭': 'crying',
  '🤔': 'thinking',
  '🎉': 'party',
  '❤️': 'love',
}

/** 44px 😀 button that opens a one-row emoji popover. Closed by default; Esc and outside taps close it. */
export function ReactionButton() {
  const hidden = useReactionsHidden()
  const { react, toast } = useRoomActions()
  const [open, setOpen] = useState(false)
  const [top, setTop] = useState(0)
  const box = useRef<HTMLDivElement>(null)

  const toggle = () => {
    // The panel spans the screen width just under the button, so it fits at 320px.
    setTop(Math.round(box.current?.getBoundingClientRect().bottom ?? 0) + 6)
    setOpen((o) => !o)
  }

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false)
    const onPointer = (e: PointerEvent) => {
      if (box.current && !box.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('keydown', onKey)
    document.addEventListener('pointerdown', onPointer)
    return () => {
      document.removeEventListener('keydown', onKey)
      document.removeEventListener('pointerdown', onPointer)
    }
  }, [open])

  if (hidden) return null

  const send = (emoji: string) => {
    setOpen(false)
    react(emoji).catch((err: unknown) => {
      // Tapping faster than the cooldown is normal; only real failures are worth a toast.
      if (errorCode(err) !== 'RATE_LIMITED') toast(friendlyError(err), 'error')
    })
  }

  return (
    <div className="reactions-picker" ref={box}>
      <button
        type="button"
        className="btn btn--ghost reactions-picker__toggle"
        aria-label="Send a reaction"
        aria-expanded={open}
        onClick={toggle}
      >
        😀
      </button>
      {open && (
        <div className="reactions-picker__panel" role="group" aria-label="Reactions" style={{ top }}>
          {C.REACTION_EMOJIS.map((emoji) => (
            <button key={emoji} type="button" aria-label={`React ${EMOJI_NAMES[emoji] ?? emoji}`} onClick={() => send(emoji)}>
              {emoji}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

function prefersReducedMotion(): boolean {
  return typeof window !== 'undefined' && typeof window.matchMedia === 'function'
    ? window.matchMedia('(prefers-reduced-motion: reduce)').matches
    : false
}

/** A small, stable horizontal offset per reaction so several don't stack exactly. */
function offset(id: string): number {
  let hash = 0
  for (const ch of id) hash = (hash * 31 + ch.charCodeAt(0)) | 0
  return Math.abs(hash) % 40
}

/** Incoming reactions: they float up the lower right edge and fade. Never blocks a tap. */
export function ReactionLayer({ room }: { room: RoomPublic }) {
  const hidden = useReactionsHidden()
  const { reactions } = useRoomState()
  if (hidden || reactions.length === 0) return null
  const still = prefersReducedMotion()
  return (
    <div className={`reactions${still ? ' reactions--still' : ''}`} aria-hidden="true">
      {reactions.map((r) => (
        <Reaction key={r.id} reaction={r} room={room} still={still} />
      ))}
    </div>
  )
}

function Reaction({ reaction, room, still }: { reaction: ReactionPush; room: RoomPublic; still: boolean }) {
  const player = room.players.find((p) => p.id === reaction.playerId)
  const style = still
    ? undefined
    : { right: `${offset(reaction.id)}px`, animationDuration: `${C.REACTION_DISPLAY_MS}ms` }
  return (
    <div className="reaction" style={style} data-testid="reaction">
      <span className="reaction__emoji">{reaction.emoji}</span>
      <span className="reaction__who">
        {player && !still && <Avatar avatar={player.avatar} nickname={player.nickname} color="var(--border)" />}
        <span className="reaction__name">{reaction.nickname}</span>
      </span>
    </div>
  )
}
