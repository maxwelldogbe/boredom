import { useState, type FormEvent } from 'react'
import { useSearchParams } from 'react-router-dom'
import type { UsersData } from '../api'
import { ActorLink, LoadState, Pager, Refreshing } from '../components'
import { fmtDate, fmtDateTime, fmtInt, fmtPct } from '../format'
import { useAdminSession } from '../session'
import { useAdminData } from '../useAdminData'

const SORT_LABELS: Record<string, string> = {
  games: 'Games',
  wins: 'Wins',
  win_rate: 'Win rate',
  last_seen: 'Last seen',
}

export default function UsersPage() {
  const { session } = useAdminSession()
  const [params, setParams] = useSearchParams()
  const q = params.get('q') ?? ''
  const type = params.get('type') ?? ''
  const sort = params.get('sort') ?? 'games'
  const dir = params.get('dir') ?? 'desc'
  const page = params.get('page') ?? '1'
  const [search, setSearch] = useState(q)
  const { data, error, loading, refreshing } = useAdminData<UsersData>('users', { q, type, sort, dir, page })

  const update = (changes: Record<string, string>) => {
    const next = new URLSearchParams(params)
    for (const [k, v] of Object.entries(changes)) {
      if (v) next.set(k, v)
      else next.delete(k)
    }
    if (!('page' in changes)) next.delete('page')
    setParams(next)
  }

  const submit = (e: FormEvent) => {
    e.preventDefault()
    update({ q: search.trim() })
  }

  return (
    <div className="stack">
      <h1>Users</h1>
      <form className="filters" onSubmit={submit} role="search">
        <label className="filters__field">
          <span className="visually-hidden">Search nickname or username</span>
          <input
            type="search"
            className="field__input"
            placeholder="Nickname or username"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </label>
        <label className="filters__field">
          <span className="visually-hidden">Type</span>
          <select className="field__input" value={type} onChange={(e) => update({ type: e.target.value })}>
            <option value="">Everyone</option>
            <option value="registered">Registered</option>
            <option value="guest">Guests</option>
          </select>
        </label>
        <label className="filters__field">
          <span className="visually-hidden">Sort by</span>
          <select className="field__input" value={sort} onChange={(e) => update({ sort: e.target.value })}>
            {Object.entries(SORT_LABELS).map(([k, label]) => (
              <option key={k} value={k}>
                Sort: {label}
              </option>
            ))}
          </select>
        </label>
        <label className="filters__field">
          <span className="visually-hidden">Direction</span>
          <select className="field__input" value={dir} onChange={(e) => update({ dir: e.target.value })}>
            <option value="desc">High to low</option>
            <option value="asc">Low to high</option>
          </select>
        </label>
        <button type="submit" className="btn btn--secondary">
          Search
        </button>
        <a className="filters__export" href={session.exports.users}>
          Export CSV
        </a>
      </form>
      {!data && <LoadState error={error} loading={loading} />}
      {data && (
        <Refreshing active={refreshing}>
          <div className="table-scroll card">
            <table className="admin-table">
              <thead>
                <tr>
                  <th scope="col">Player</th>
                  <th scope="col">Username</th>
                  <th scope="col">First seen</th>
                  <th scope="col">Last seen</th>
                  <th scope="col" className="num">Games</th>
                  <th scope="col" className="num">Wins</th>
                  <th scope="col" className="num">Losses</th>
                  <th scope="col" className="num">Win rate</th>
                  <th scope="col">Favorite</th>
                </tr>
              </thead>
              <tbody>
                {data.results.length === 0 && (
                  <tr>
                    <td colSpan={9} className="muted">
                      No players match.
                    </td>
                  </tr>
                )}
                {data.results.map((u) => (
                  <tr key={`${u.kind}-${u.userId ?? u.guestKey}`}>
                    <td>
                      <ActorLink actor={u} />
                    </td>
                    <td>{u.username ?? '—'}</td>
                    <td>{fmtDate(u.firstSeen, session.timeZone)}</td>
                    <td>{fmtDateTime(u.lastSeen, session.timeZone)}</td>
                    <td className="num">{fmtInt(u.games)}</td>
                    <td className="num">{fmtInt(u.wins)}</td>
                    <td className="num">{fmtInt(u.losses)}</td>
                    <td className="num">{fmtPct(u.winRate)}</td>
                    <td>{u.favorite?.name ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pager page={data} onPage={(n) => update({ page: String(n) })} />
          <p className="muted small">
            Win rate appears after {data.minGamesForRates} completed games. Guests are approximate (one browser = one
            guest) and are listed once they have played.
          </p>
        </Refreshing>
      )}
    </div>
  )
}
