/** The registered profile page's sections: header, stats, by game and recent players.
 *  Every number comes from the server; each section loads (and fails) on its own. */
import { useState, type CSSProperties } from 'react'
import { Avatar } from '../../components/Avatar'
import { Button } from '../../components/Button'
import { CopyButton } from '../../components/CopyButton'
import { Modal } from '../../components/Modal'
import { gameUi } from '../../games/registry'
import type { MyStats, RecentPlayer } from '../../lib/account'
import { formatRate, monthYear, timeAgo } from '../../lib/format'
import type { Avatar as AvatarData, GameId } from '../../types/protocol'
import type { Load } from './useLoad'

function Skeleton({ label, lines = 2 }: { label: string; lines?: number }) {
  return (
    <div className="skeleton" role="status" aria-label={label}>
      {Array.from({ length: lines }, (_, i) => (
        <span key={i} className="skeleton__line" aria-hidden="true" />
      ))}
    </div>
  )
}

function LoadError({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="profile__error" role="alert">
      <p>{message}</p>
      <Button variant="secondary" onClick={onRetry}>
        Retry
      </Button>
    </div>
  )
}

// ----- shared bits -----------------------------------------------------------------------------

/** An avatar inside a 3px ring of the player's color. */
export function RingAvatar({ avatar, nickname, color, size }: { avatar?: AvatarData; nickname: string; color: string; size: number }) {
  return (
    <span className="ring-avatar" style={{ '--ring-size': `${size}px`, borderColor: color } as CSSProperties}>
      <Avatar avatar={avatar} nickname={nickname} color="var(--border)" />
    </span>
  )
}

function TagChip({ tag }: { tag: string }) {
  return (
    <span className="tag-chip">
      <span className="tag-chip__code" aria-label={`Tag #${tag.split('').join(' ')}`}>
        #{tag}
      </span>
      <CopyButton text={`#${tag}`} label="Copy" ariaLabel="Copy tag" copiedMessage="Tag copied" block={false} />
    </span>
  )
}

const times = (n: number) => `${n} time${n === 1 ? '' : 's'}`

// ----- header ----------------------------------------------------------------------------------

export interface HeaderData {
  tag?: string
  createdAt?: string
}

export function ProfileHeader({
  nickname,
  color,
  avatar,
  me,
  onRetry,
}: {
  nickname: string
  color: string
  avatar?: AvatarData
  me: Load<HeaderData>
  onRetry: () => void
}) {
  return (
    <header className="card profile__header">
      <RingAvatar avatar={avatar} nickname={nickname} color={color} size={96} />
      <div className="profile__who">
        <h1 className="profile__name">{nickname}</h1>
        {me.status === 'loading' && <Skeleton label="Loading your tag" lines={1} />}
        {me.status === 'error' && <LoadError message={me.message} onRetry={onRetry} />}
        {me.status === 'ready' && (
          <>
            {me.data.tag && <TagChip tag={me.data.tag} />}
            {me.data.createdAt && <p className="muted">Member since {monthYear(me.data.createdAt)}</p>}
          </>
        )}
      </div>
    </header>
  )
}

// ----- stats -----------------------------------------------------------------------------------

function StatCard({ label, value, note }: { label: string; value: string | number; note?: string }) {
  return (
    <li className="stat-card">
      <span className="stat-card__value">{value}</span>
      <span className="stat-card__label">{label}</span>
      {note && <span className="stat-card__note">{note}</span>}
    </li>
  )
}

export function StatsSection({ stats, onRetry }: { stats: Load<MyStats>; onRetry: () => void }) {
  return (
    <section className="stack" aria-labelledby="stats-heading">
      <h2 id="stats-heading">Stats</h2>
      {stats.status === 'loading' && <Skeleton label="Loading your stats" lines={3} />}
      {stats.status === 'error' && <LoadError message={stats.message} onRetry={onRetry} />}
      {stats.status === 'ready' &&
        (stats.data.totals.played === 0 ? (
          <p className="muted profile__empty">Play a game to see your stats here</p>
        ) : (
          <>
            <ul className="stat-cards">
              <StatCard label="Games" value={stats.data.totals.played} />
              <StatCard label="Wins" value={stats.data.totals.wins} />
              <StatCard label="Losses" value={stats.data.totals.losses} />
              <StatCard
                label="Win rate"
                value={formatRate(stats.data.totals.winRate)}
                note={stats.data.totals.winRate === null ? `Win rate shows after ${stats.data.minGamesForRate} games` : undefined}
              />
            </ul>
            {stats.data.favoriteGame && <FavoriteGame gameId={stats.data.favoriteGame} />}
          </>
        ))}
    </section>
  )
}

function FavoriteGame({ gameId }: { gameId: GameId }) {
  const game = gameUi(gameId)
  return (
    <p className="profile__favorite">
      Favorite game:{' '}
      <strong>
        <span aria-hidden="true">{game?.icon} </span>
        {game?.name ?? gameId}
      </strong>
    </p>
  )
}

export function ByGameSection({ stats, onRetry }: { stats: Load<MyStats>; onRetry: () => void }) {
  return (
    <section className="stack" aria-labelledby="bygame-heading">
      <h2 id="bygame-heading">By game</h2>
      {stats.status === 'loading' && <Skeleton label="Loading your games" lines={3} />}
      {stats.status === 'error' && <LoadError message={stats.message} onRetry={onRetry} />}
      {stats.status === 'ready' &&
        (stats.data.perGame.length === 0 ? (
          <p className="muted profile__empty">Play a game to see your stats here</p>
        ) : (
          <ul className="bygame">
            {stats.data.perGame.map((g) => {
              const game = gameUi(g.gameId)
              return (
                <li key={g.gameId} className="bygame__row">
                  <span className="bygame__name">
                    <span aria-hidden="true">{game?.icon} </span>
                    {game?.name ?? g.gameId}
                  </span>
                  <span className="bygame__nums">
                    <span>{g.played} played</span>
                    <span>{g.wins} won</span>
                    <span>{formatRate(g.winRate)}</span>
                  </span>
                </li>
              )
            })}
          </ul>
        ))}
    </section>
  )
}

// ----- recent players --------------------------------------------------------------------------

function PlayerLines({ player }: { player: RecentPlayer }) {
  return (
    <>
      <span className="recent__line">Played together {times(player.gamesTogether)}</span>
      <span className="recent__line">Last played {timeAgo(player.lastPlayedAt)}</span>
    </>
  )
}

export function RecentPlayersSection({ players, onRetry }: { players: Load<RecentPlayer[]>; onRetry: () => void }) {
  const [open, setOpen] = useState<RecentPlayer | null>(null)
  return (
    <section className="stack" aria-labelledby="recent-heading">
      <h2 id="recent-heading">Recent players</h2>
      {players.status === 'loading' && <Skeleton label="Loading recent players" lines={2} />}
      {players.status === 'error' && <LoadError message={players.message} onRetry={onRetry} />}
      {players.status === 'ready' &&
        (players.data.length === 0 ? (
          <p className="muted profile__empty">Players you play with will show up here</p>
        ) : (
          <ul className="recent">
            {players.data.map((p) => (
              <li key={p.tag}>
                <button type="button" className="recent__card" onClick={() => setOpen(p)}>
                  <RingAvatar avatar={p.avatar} nickname={p.nickname} color={p.color} size={48} />
                  <span className="recent__info">
                    <span className="recent__name">
                      {p.nickname} <span className="muted">#{p.tag}</span>
                    </span>
                    <PlayerLines player={p} />
                  </span>
                </button>
              </li>
            ))}
          </ul>
        ))}
      {open && (
        <Modal
          title={open.nickname}
          onClose={() => setOpen(null)}
          actions={
            <Button variant="secondary" block onClick={() => setOpen(null)}>
              Close
            </Button>
          }
        >
          <div className="recent__detail">
            <RingAvatar avatar={open.avatar} nickname={open.nickname} color={open.color} size={80} />
            <TagChip tag={open.tag} />
            <PlayerLines player={open} />
          </div>
        </Modal>
      )}
    </section>
  )
}
