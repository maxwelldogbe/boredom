import { Link, useSearchParams } from 'react-router-dom'
import type { GamesData } from '../api'
import { InlineBar, LoadState, RangeFilter, Refreshing } from '../components'
import { fmtDuration, fmtInt, fmtNum, fmtPct } from '../format'
import { useAdminData } from '../useAdminData'

export default function GamesPage() {
  const [params, setParams] = useSearchParams()
  const range = params.get('range') ?? '7d'
  const { data, error, loading, refreshing } = useAdminData<GamesData>('games', { range })
  const maxPlays = Math.max(0, ...(data?.games.map((g) => g.plays) ?? []))

  return (
    <div className="stack">
      <h1>Games</h1>
      {data && <RangeFilter ranges={data.ranges} value={data.range.key} onChange={(r) => setParams({ range: r })} />}
      {!data && <LoadState error={error} loading={loading} />}
      {data && (
        <Refreshing active={refreshing}>
          <div className="table-scroll card">
            <table className="admin-table">
              <thead>
                <tr>
                  <th scope="col">Game</th>
                  <th scope="col" className="num">Plays</th>
                  <th scope="col" className="num">Unique players</th>
                  <th scope="col" className="num">Avg players</th>
                  <th scope="col" className="num">Avg duration</th>
                  <th scope="col" className="num">Completion</th>
                  <th scope="col" className="num">Abandoned</th>
                </tr>
              </thead>
              <tbody>
                {data.games.map((g) => (
                  <tr key={g.id}>
                    <td>
                      <Link to={`/admin/games/${g.id}?range=${data.range.key}`}>{g.name}</Link>
                    </td>
                    <td className="num">
                      <span className="bar-cell">
                        <InlineBar value={g.plays} max={maxPlays} />
                        {fmtInt(g.plays)}
                      </span>
                    </td>
                    <td className="num">{fmtInt(g.uniquePlayers)}</td>
                    <td className="num">{fmtNum(g.avgPlayers)}</td>
                    <td className="num">{fmtDuration(g.avgDuration)}</td>
                    <td className="num">{fmtPct(g.completionRate)}</td>
                    <td className="num">{fmtInt(g.abandoned)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="muted small">Plays count completed games. Completion = completed ÷ (completed + abandoned).</p>
        </Refreshing>
      )}
    </div>
  )
}
