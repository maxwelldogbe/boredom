import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { Button } from '../../components/Button'
import { Modal } from '../../components/Modal'
import { useRoomActions } from '../../state/context'
import { AdminApiError, userAction, type UserDetailData } from '../api'
import { ActorLink, LoadState, Refreshing, StatTile, TypeBadge } from '../components'
import { fmtDate, fmtDateTime, fmtInt, fmtNum, fmtPct } from '../format'
import { useAdminSession } from '../session'
import { useAdminData } from '../useAdminData'

export default function UserDetailPage({ kind }: { kind: 'registered' | 'guest' }) {
  const { userId = '', guestKey = '' } = useParams()
  const path = kind === 'registered' ? `users/u/${encodeURIComponent(userId)}` : `users/g/${encodeURIComponent(guestKey)}`
  const { session } = useAdminSession()
  const { data, error, loading, refreshing, reload } = useAdminData<UserDetailData>(path)

  return (
    <div className="stack">
      <Link to="/admin/users" className="back-link">
        ← Users
      </Link>
      {!data && <LoadState error={error} loading={loading} />}
      {data && (
        <Refreshing active={refreshing}>
          <div className="stack">
            <header className="detail-head">
              <h1>{data.actor.name}</h1>
              <TypeBadge actor={data.actor} />
              {data.actor.isActive === false && <span className="badge badge--warn">disabled</span>}
            </header>
            <p className="muted">
              {data.actor.kind === 'registered'
                ? `Username ${data.actor.username}, joined ${fmtDate(data.actor.joined, session.timeZone)}.`
                : 'Guest: approximate (browser-based). One browser profile counts as one guest.'}
            </p>
            {data.actor.kind === 'registered' && data.actor.userId !== null && (
              <AccountActions data={data} userId={data.actor.userId} onChanged={reload} />
            )}

            <section className="stats" aria-label="Totals">
              <StatTile label="Games" value={fmtInt(data.totals.games)} hint={`${fmtInt(data.totals.abandoned)} abandoned`} />
              <StatTile label="Wins" value={fmtInt(data.totals.wins)} />
              <StatTile label="Losses" value={fmtInt(data.totals.losses)} />
              <StatTile
                label="Win rate"
                value={fmtPct(data.totals.winRate)}
                hint={data.totals.winRate === null ? `After ${data.minGamesForRates} games` : undefined}
              />
              <StatTile label="Most played" value={data.mostPlayed?.name ?? '—'} />
              <StatTile label="Most won" value={data.mostWon?.name ?? '—'} />
              <StatTile label="Most lost" value={data.mostLost?.name ?? '—'} />
            </section>

            <section className="card stack" aria-labelledby="by-game">
              <h2 id="by-game">By game</h2>
              {data.perGame.length === 0 ? (
                <p className="muted">No completed games yet.</p>
              ) : (
                <div className="table-scroll">
                  <table className="admin-table">
                    <thead>
                      <tr>
                        <th scope="col">Game</th>
                        <th scope="col" className="num">Played</th>
                        <th scope="col" className="num">Wins</th>
                        <th scope="col" className="num">Losses</th>
                        <th scope="col" className="num">Win rate</th>
                        <th scope="col" className="num">Avg place</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.perGame.map((g) => (
                        <tr key={g.id}>
                          <td>
                            <Link to={`/admin/games/${g.id}`}>{g.name}</Link>
                          </td>
                          <td className="num">{g.played}</td>
                          <td className="num">{g.wins}</td>
                          <td className="num">{g.losses}</td>
                          <td className="num">{fmtPct(g.winRate)}</td>
                          <td className="num">{fmtNum(g.avgPlacement)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>

            <div className="two-col">
              <section className="card stack" aria-labelledby="last-games">
                <h2 id="last-games">Last 20 games</h2>
                {data.recent.length === 0 ? (
                  <p className="muted">No games yet.</p>
                ) : (
                  <div className="table-scroll">
                    <table className="admin-table">
                      <thead>
                        <tr>
                          <th scope="col">When</th>
                          <th scope="col">Game</th>
                          <th scope="col" className="num">Place</th>
                          <th scope="col">Opponents</th>
                        </tr>
                      </thead>
                      <tbody>
                        {data.recent.map((p, i) => (
                          <tr key={i}>
                            <td>{fmtDateTime(p.startedAt, session.timeZone)}</td>
                            <td>{p.game?.name ?? '—'}</td>
                            <td className="num">
                              {p.placement ?? <span className="muted">{p.status}</span>}
                              {p.leftEarly && <span className="badge">left</span>}
                            </td>
                            <td>{p.opponents.join(', ') || '—'}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </section>
              <section className="card stack" aria-labelledby="co-players">
                <h2 id="co-players">Top co-players</h2>
                {data.coPlayers.length === 0 ? (
                  <p className="muted">Nobody yet.</p>
                ) : (
                  <div className="table-scroll">
                    <table className="admin-table">
                      <thead>
                        <tr>
                          <th scope="col">Player</th>
                          <th scope="col" className="num">Shared</th>
                          <th scope="col" className="num">Ahead</th>
                          <th scope="col" className="num">Behind</th>
                        </tr>
                      </thead>
                      <tbody>
                        {data.coPlayers.map((c) => (
                          <tr key={`${c.kind}-${c.userId ?? c.guestKey}`}>
                            <td>
                              <ActorLink actor={c} />
                            </td>
                            <td className="num">{c.shared}</td>
                            <td className="num">{c.ahead}</td>
                            <td className="num">{c.behind}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </section>
            </div>

            <section className="card stack" aria-labelledby="timeline">
              <h2 id="timeline">Activity timeline</h2>
              {data.events.length === 0 ? (
                <p className="muted">No recent activity (events are kept for a limited time).</p>
              ) : (
                <ol className="timeline">
                  {data.events.map((e) => (
                    <li key={e.id}>
                      <time dateTime={e.occurredAt}>{fmtDateTime(e.occurredAt, session.timeZone)}</time>
                      <span>
                        {e.label}
                        {e.roomCode && <span className="muted"> · room {e.roomCode}</span>}
                        {e.game && <span className="muted"> · {e.game.name}</span>}
                      </span>
                    </li>
                  ))}
                </ol>
              )}
            </section>
          </div>
        </Refreshing>
      )}
    </div>
  )
}

function AccountActions({ data, userId, onChanged }: { data: UserDetailData; userId: number; onChanged: () => void }) {
  const { session, onUnauthorized } = useAdminSession()
  const { toast } = useRoomActions()
  const navigate = useNavigate()
  const [busy, setBusy] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)
  if (!data.permissions.change && !data.permissions.delete) return null

  const run = async (action: 'disable' | 'enable' | 'delete') => {
    setBusy(true)
    try {
      await userAction(userId, action, session.csrfToken)
      if (action === 'delete') {
        toast('Account deleted. Its games are kept as “Deleted player”.')
        navigate('/admin/users', { replace: true })
        return
      }
      toast(action === 'disable' ? 'Account disabled.' : 'Account enabled.')
      onChanged()
    } catch (err) {
      if (err instanceof AdminApiError && err.status === 401) onUnauthorized()
      toast(err instanceof Error ? err.message : 'That did not work.', 'error')
    } finally {
      setBusy(false)
      setConfirmDelete(false)
    }
  }

  return (
    <div className="actions">
      {data.permissions.change &&
        (data.actor.isActive ? (
          <Button variant="secondary" disabled={busy} onClick={() => run('disable')}>
            Disable account
          </Button>
        ) : (
          <Button variant="secondary" disabled={busy} onClick={() => run('enable')}>
            Enable account
          </Button>
        ))}
      {data.permissions.delete && (
        <Button variant="danger" disabled={busy} onClick={() => setConfirmDelete(true)}>
          Delete account
        </Button>
      )}
      {confirmDelete && (
        <Modal
          title={`Delete ${data.actor.username}?`}
          onClose={() => setConfirmDelete(false)}
          actions={
            <>
              <Button variant="danger" block disabled={busy} onClick={() => run('delete')}>
                {busy ? 'Deleting…' : 'Yes, delete the account'}
              </Button>
              <Button variant="secondary" block disabled={busy} onClick={() => setConfirmDelete(false)}>
                Cancel
              </Button>
            </>
          }
        >
          <p>
            The login, saved profile and stats are deleted. Their past games stay in the totals as “Deleted player”.
            This cannot be undone.
          </p>
        </Modal>
      )}
    </div>
  )
}
