import type { ReactNode } from 'react'
import { playerById } from '../lib/players'
import { onSeatColor, seatColor } from '../lib/seatColors'
import type { RoomPublic } from '../types/protocol'
import { Avatar } from './Avatar'

export interface PlayerCardEntry {
  id: string
  /** Big number on the right (score, dice left…). */
  value?: ReactNode
  /** Accessible name for the value, e.g. "3 dice". */
  valueLabel?: string
  /** Short notes under the name ("host", "✖ out"…). "offline" is added automatically. */
  notes?: ReactNode[]
}

interface PlayerCardsProps {
  room: RoomPublic
  me: string
  entries: PlayerCardEntry[]
  /** The player whose turn it is; their card fills with their seat colour. */
  activeId?: string | null
  label?: string
}

/** The shared player banner: one card per player, seat colour ring, active player filled in. */
export function PlayerCards({ room, me, entries, activeId, label = 'Players' }: PlayerCardsProps) {
  const cols = Math.min(Math.max(entries.length, 2), 4)
  return (
    <ul className={`player-cards player-cards--cols-${cols}`} aria-label={label}>
      {entries.map(({ id, value, valueLabel, notes = [] }) => {
        const player = playerById(room, id)
        const active = id === activeId
        const allNotes = player.online ? notes : [...notes, 'offline']
        return (
          <li
            key={id}
            className={`player-card${active ? ' player-card--active' : ''}`}
            aria-current={active ? 'true' : undefined}
            style={active ? { background: seatColor(room, id), color: onSeatColor(room, id), transform: 'scale(1.04)' } : undefined}
          >
            <span className="player-card__ring" style={{ borderColor: active ? '#FFFFFF' : seatColor(room, id) }}>
              <Avatar avatar={player.avatar} nickname={player.nickname} color="var(--border)" />
            </span>
            <span className="player-card__info">
              <span className="player-card__name">
                {player.nickname}
                {id === me && <small className="player-card__you">You</small>}
              </span>
              {allNotes.length > 0 && (
                <span className="player-card__notes">
                  {allNotes.map((note, i) => (
                    <span key={i} className="player-card__note">
                      {note}
                    </span>
                  ))}
                </span>
              )}
            </span>
            {value !== undefined && (
              <strong className="player-card__value" aria-label={valueLabel}>
                {value}
              </strong>
            )}
          </li>
        )
      })}
    </ul>
  )
}
