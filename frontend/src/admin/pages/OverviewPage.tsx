import { Link, useSearchParams } from 'react-router-dom'
import type { OverviewData } from '../api'
import { DailyColumns, LoadState, RangeFilter, Refreshing, StatTile } from '../components'
import { fmtDuration, fmtInt, fmtNum, fmtPct } from '../format'
import { useAdminData } from '../useAdminData'

export default function OverviewPage() {
  const [params, setParams] = useSearchParams()
  const range = params.get('range') ?? '7d'
  const { data, error, loading, refreshing } = useAdminData<OverviewData>('overview', { range })

  return (
    <div className="stack">
      <h1>Overview</h1>
      {data && <RangeFilter ranges={data.ranges} value={data.range.key} onChange={(r) => setParams({ range: r })} />}
      {!data && <LoadState error={error} loading={loading} />}
      {data && (
        <Refreshing active={refreshing}>
          <div className="stack">
            <section className="stats" aria-label="Key numbers">
              <StatTile label="Registered users" value={fmtInt(data.users.total)} hint={`${fmtInt(data.users.new)} new, ${data.range.label.toLowerCase()}`} />
              <StatTile label="Guests seen" value={fmtInt(data.guestsSeen)} hint="Approximate (browser-based)" />
              <StatTile label="Active today" value={fmtInt(data.active.daily)} hint="Last 24 hours" />
              <StatTile label="Active this week" value={fmtInt(data.active.weekly)} hint="Last 7 days" />
              <StatTile label="Active this month" value={fmtInt(data.active.monthly)} hint="Last 30 days" />
              <StatTile label="Completed games" value={fmtInt(data.sessions.completed)} hint={data.range.label} />
              <StatTile label="Games today" value={fmtInt(data.sessions.today)} />
              <StatTile label="Avg players per game" value={fmtNum(data.sessions.avgPlayers)} />
              <StatTile label="Avg duration" value={fmtDuration(data.sessions.avgDuration)} />
              <StatTile label="Abandon rate" value={fmtPct(data.sessions.abandonRate)} hint={`${fmtInt(data.sessions.abandoned)} abandoned`} />
              <StatTile
                label="Most played"
                value={data.mostPlayed ? <Link to={`/admin/games/${data.mostPlayed.id}`}>{data.mostPlayed.name}</Link> : '—'}
                hint={data.mostPlayed ? `${fmtInt(data.mostPlayed.plays)} plays` : undefined}
              />
            </section>

            <section className="card stack" aria-labelledby="per-day">
              <h2 id="per-day">Completed games per day, last 30 days</h2>
              <DailyColumns series={data.perDay} label="Completed games per day, last 30 days" />
            </section>

            <section className="card stack" aria-labelledby="live">
              <h2 id="live">Live now</h2>
              <p className="muted">
                {data.live.length} room{data.live.length === 1 ? '' : 's'} open,{' '}
                {data.live.reduce((n, r) => n + r.players, 0)} players seated. A read-only snapshot of the server's memory.
              </p>
              {data.live.length > 0 && (
                <div className="table-scroll">
                  <table className="admin-table">
                    <thead>
                      <tr>
                        <th scope="col">Room</th>
                        <th scope="col">Status</th>
                        <th scope="col">Game</th>
                        <th scope="col" className="num">Players</th>
                        <th scope="col" className="num">Online</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.live.map((r) => (
                        <tr key={r.code}>
                          <td className="mono">{r.code}</td>
                          <td>{r.status}</td>
                          <td>{r.game}</td>
                          <td className="num">{r.players}</td>
                          <td className="num">{r.online}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>
            <p className="muted small">Numbers refresh at most every {data.cachedSeconds} seconds.</p>
          </div>
        </Refreshing>
      )}
    </div>
  )
}
