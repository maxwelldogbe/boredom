import { useSearchParams } from 'react-router-dom'
import { C } from '../../lib/constants'
import type { ActivityData } from '../api'
import { ActorLink, LoadState, Pager, Refreshing } from '../components'
import { fmtDateTime } from '../format'
import { useAdminSession } from '../session'
import { useAdminData } from '../useAdminData'

export default function ActivityPage() {
  const { session } = useAdminSession()
  const [params, setParams] = useSearchParams()
  const kind = params.get('kind') ?? ''
  const game = params.get('game') ?? ''
  const date = params.get('date') ?? ''
  const page = params.get('page') ?? '1'
  const { data, error, loading, refreshing } = useAdminData<ActivityData>('activity', { kind, game, date, page })

  const update = (key: string, value: string) => {
    const next = new URLSearchParams(params)
    if (value) next.set(key, value)
    else next.delete(key)
    if (key !== 'page') next.delete('page')
    setParams(next)
  }

  return (
    <div className="stack">
      <h1>Activity</h1>
      <div className="filters">
        <label className="filters__field">
          <span className="visually-hidden">Kind</span>
          <select className="field__input" value={kind} onChange={(e) => update('kind', e.target.value)}>
            <option value="">All kinds</option>
            {data?.kinds.map((k) => (
              <option key={k.value} value={k.value}>
                {k.label}
              </option>
            ))}
          </select>
        </label>
        <label className="filters__field">
          <span className="visually-hidden">Game</span>
          <select className="field__input" value={game} onChange={(e) => update('game', e.target.value)}>
            <option value="">All games</option>
            {data?.games.map((g) => (
              <option key={g.id} value={g.id}>
                {g.name}
              </option>
            ))}
          </select>
        </label>
        <label className="filters__field">
          <span className="visually-hidden">Date</span>
          <input type="date" className="field__input" value={date} onChange={(e) => update('date', e.target.value)} />
        </label>
        <a className="filters__export" href={session.exports.sessions}>
          Export game sessions CSV
        </a>
      </div>
      {!data && <LoadState error={error} loading={loading} />}
      {data && (
        <Refreshing active={refreshing}>
          <div className="table-scroll card">
            <table className="admin-table">
              <thead>
                <tr>
                  <th scope="col">When</th>
                  <th scope="col">Event</th>
                  <th scope="col">Who</th>
                  <th scope="col">Room</th>
                  <th scope="col">Game</th>
                </tr>
              </thead>
              <tbody>
                {data.results.length === 0 && (
                  <tr>
                    <td colSpan={5} className="muted">
                      No events.
                    </td>
                  </tr>
                )}
                {data.results.map((e) => (
                  <tr key={e.id}>
                    <td>{fmtDateTime(e.occurredAt, session.timeZone)}</td>
                    <td>{e.label}</td>
                    <td>{e.who ? <ActorLink actor={e.who} /> : <span className="muted">—</span>}</td>
                    <td className="mono">{e.roomCode || '—'}</td>
                    <td>{e.game?.name ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pager page={data} onPage={(n) => update('page', String(n))} />
          <p className="muted small">Newest first. Events are kept for {C.ACTIVITY_RETENTION_DAYS} days; game results forever.</p>
        </Refreshing>
      )}
    </div>
  )
}
