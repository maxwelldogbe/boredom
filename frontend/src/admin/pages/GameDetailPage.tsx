import { Link, useParams, useSearchParams } from 'react-router-dom'
import type { GameDetailData } from '../api'
import { DailyColumns, LoadState, RangeFilter, Refreshing, StatTile } from '../components'
import { fmtDateTime, fmtDuration, fmtInt, fmtNum, fmtPct } from '../format'
import { useAdminSession } from '../session'
import { useAdminData } from '../useAdminData'

export default function GameDetailPage() {
  const { gameId = '' } = useParams()
  const [params, setParams] = useSearchParams()
  const range = params.get('range') ?? '7d'
  const { session } = useAdminSession()
  const { data, error, loading, refreshing } = useAdminData<GameDetailData>(`games/${encodeURIComponent(gameId)}`, { range })

  return (
    <div className="stack">
      <Link to="/admin/games" className="back-link">
        ← Games
      </Link>
      <h1>{data?.game.name ?? 'Game'}</h1>
      {data && <RangeFilter ranges={data.ranges} value={data.range.key} onChange={(r) => setParams({ range: r })} />}
      {!data && <LoadState error={error} loading={loading} />}
      {data && (
        <Refreshing active={refreshing}>
          <div className="stack">
            <section className="stats" aria-label="Key numbers">
              <StatTile label="Plays" value={fmtInt(data.totals.plays)} hint={data.range.label} />
              <StatTile label="Unique players" value={fmtInt(data.totals.uniquePlayers)} />
              <StatTile label="Avg players" value={fmtNum(data.totals.avgPlayers)} />
              <StatTile label="Avg duration" value={fmtDuration(data.totals.avgDuration)} />
              <StatTile label="Completion" value={fmtPct(data.totals.completionRate)} hint={`${fmtInt(data.totals.abandoned)} abandoned`} />
            </section>
            <section className="card stack" aria-labelledby="game-per-day">
              <h2 id="game-per-day">Plays per day, last 30 days</h2>
              <DailyColumns series={data.perDay} label={`${data.game.name} plays per day, last 30 days`} unit="plays" />
            </section>
            <section className="card stack" aria-labelledby="recent">
              <h2 id="recent">Recent sessions</h2>
              {data.recent.length === 0 ? (
                <p className="muted">No sessions yet.</p>
              ) : (
                <div className="table-scroll">
                  <table className="admin-table">
                    <thead>
                      <tr>
                        <th scope="col">Started</th>
                        <th scope="col">Status</th>
                        <th scope="col" className="num">Players</th>
                        <th scope="col" className="num">Duration</th>
                        <th scope="col">Room</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.recent.map((s) => (
                        <tr key={s.id}>
                          <td>{fmtDateTime(s.startedAt, session.timeZone)}</td>
                          <td>{s.status}</td>
                          <td className="num">{s.playerCount}</td>
                          <td className="num">{fmtDuration(s.durationSeconds)}</td>
                          <td className="mono">{s.roomCode}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>
            <Link to={`/admin/leaderboards?game=${data.game.id}`}>Leaderboard for {data.game.name} →</Link>
          </div>
        </Refreshing>
      )}
    </div>
  )
}
