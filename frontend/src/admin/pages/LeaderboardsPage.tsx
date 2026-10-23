import { useSearchParams } from 'react-router-dom'
import type { LeaderboardsData, LeaderRow } from '../api'
import { ActorLink, LoadState, Refreshing } from '../components'
import { fmtInt, fmtPct } from '../format'
import { useAdminData } from '../useAdminData'

function Board({ title, rows, metric }: { title: string; rows: LeaderRow[]; metric: 'wins' | 'winRate' | 'games' }) {
  return (
    <section className="card stack" aria-label={title}>
      <h2>{title}</h2>
      {rows.length === 0 ? (
        <p className="muted">Nobody yet.</p>
      ) : (
        <table className="admin-table">
          <thead>
            <tr>
              <th scope="col" className="num">#</th>
              <th scope="col">Player</th>
              <th scope="col" className="num">{metric === 'winRate' ? 'Win rate' : metric === 'wins' ? 'Wins' : 'Games'}</th>
              <th scope="col" className="num">Games</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={`${r.kind}-${r.userId ?? r.guestKey}`}>
                <td className="num">{i + 1}</td>
                <td>
                  <ActorLink actor={r} />
                </td>
                <td className="num">
                  {metric === 'winRate' ? fmtPct(r.winRate) : fmtInt(metric === 'wins' ? r.wins : r.games)}
                </td>
                <td className="num">{fmtInt(r.games)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  )
}

export default function LeaderboardsPage() {
  const [params, setParams] = useSearchParams()
  const game = params.get('game') ?? ''
  const { data, error, loading, refreshing } = useAdminData<LeaderboardsData>('leaderboards', { game })

  return (
    <div className="stack">
      <h1>Leaderboards</h1>
      <div className="filters">
        <label className="filters__field">
          <span className="visually-hidden">Game</span>
          <select className="field__input" value={game} onChange={(e) => setParams(e.target.value ? { game: e.target.value } : {})}>
            <option value="">Overall</option>
            {data?.games.map((g) => (
              <option key={g.id} value={g.id}>
                {g.name}
              </option>
            ))}
          </select>
        </label>
      </div>
      {!data && <LoadState error={error} loading={loading} />}
      {data && (
        <Refreshing active={refreshing}>
          <div className="three-col">
            <Board title="Most wins" rows={data.mostWins} metric="wins" />
            <Board title="Best win rate" rows={data.bestRate} metric="winRate" />
            <Board title="Most games played" rows={data.mostGames} metric="games" />
          </div>
          <p className="muted small">
            Completed games only. Best win rate needs at least {data.minGamesForRates} games.
          </p>
        </Refreshing>
      )}
    </div>
  )
}
