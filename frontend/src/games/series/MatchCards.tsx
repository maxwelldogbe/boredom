import { Avatar } from '../../components/Avatar'
import { BotIcon } from '../../components/BotIcon'
import { difficultyLabel } from '../../lib/solo'
import { playerById } from '../../lib/players'
import type { RoomPublic } from '../../types/protocol'
import { MATCH_SEAT_COLORS, MATCH_SEAT_ON_COLOR } from './matchColors'

interface MatchCardsProps {
  room: RoomPublic
  me: string
  /** Seat 1 then seat 2. */
  seats: [string, string]
  scores: Record<string, number>
  /** Accessible name for a score, e.g. "1 game won". */
  scoreLabel: (score: number) => string
  /** The player to act; their card fills with their seat colour. */
  activeId?: string | null
}

/** The two players of a match, in the same look as the shared player cards. */
export function MatchCards({ room, me, seats, scores, scoreLabel, activeId }: MatchCardsProps) {
  return (
    <ul className="player-cards player-cards--cols-2" aria-label="Match players">
      {seats.map((id, seat) => {
        const player = playerById(room, id)
        const color = MATCH_SEAT_COLORS[seat]
        const active = id === activeId
        const score = scores[id] ?? 0
        return (
          <li
            key={id}
            className={`player-card${active ? ' player-card--active' : ''}`}
            aria-current={active ? 'true' : undefined}
            style={active ? { background: color, color: MATCH_SEAT_ON_COLOR, transform: 'scale(1.04)' } : undefined}
          >
            <span className="player-card__ring" style={{ borderColor: active ? MATCH_SEAT_ON_COLOR : color }}>
              {player.bot ? (
                <span className="chip__avatar player-card__bot">
                  <BotIcon />
                </span>
              ) : (
                <Avatar avatar={player.avatar} nickname={player.nickname} color="var(--border)" />
              )}
            </span>
            <span className="player-card__info">
              <span className="player-card__name">
                {player.bot ? `Bot (${difficultyLabel(room.soloVariant?.difficulty ?? 'medium')})` : player.nickname}
                {id === me && <small className="player-card__you">You</small>}
              </span>
              {!player.online && (
                <span className="player-card__notes">
                  <span className="player-card__note">offline</span>
                </span>
              )}
            </span>
            <strong className="player-card__value" aria-label={scoreLabel(score)}>
              {score}
            </strong>
          </li>
        )
      })}
    </ul>
  )
}
