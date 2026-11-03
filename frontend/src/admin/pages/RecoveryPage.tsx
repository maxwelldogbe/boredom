import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Button } from '../../components/Button'
import { AdminApiError, adminSend, type RecoveryRequestRow, type RecoveryData } from '../api'
import { LoadState, Pager, Refreshing } from '../components'
import { useAdminSession } from '../session'
import { useAdminData } from '../useAdminData'

/** Account recovery for players who never added a recovery number: compare, then decide. */
export default function RecoveryPage() {
  const [params, setParams] = useSearchParams()
  const status = params.get('status') ?? 'pending'
  const page = params.get('page') ?? '1'
  const { data, error, loading, refreshing, reload } = useAdminData<RecoveryData>('recovery', { status, page })

  return (
    <div className="stack">
      <h1>Account recovery</h1>
      <p className="muted">
        Approve only when the answers match the account. Approving texts a one-time code to the number the player
        gave; with it they set a new password, and that number becomes their recovery number.
      </p>
      <div className="admin-filters" role="group" aria-label="Status">
        {['pending', 'approved', 'completed', 'rejected', ''].map((s) => (
          <Button key={s || 'all'} variant={status === s ? 'primary' : 'secondary'} onClick={() => setParams({ status: s })}>
            {s ? s[0].toUpperCase() + s.slice(1) : 'All'}
            {s === 'pending' && data ? ` (${data.pending})` : ''}
          </Button>
        ))}
      </div>
      {!data && <LoadState error={error} loading={loading} />}
      {data && (
        <Refreshing active={refreshing}>
          {data.results.length === 0 ? (
            <p className="muted">No requests here.</p>
          ) : (
            data.results.map((r) => <RequestCard key={r.id} request={r} onDone={reload} />)
          )}
          <Pager page={data} onPage={(n) => setParams({ status, page: String(n) })} />
        </Refreshing>
      )}
    </div>
  )
}

function Compare({ label, said, actual }: { label: string; said?: string; actual: string | null | undefined }) {
  return (
    <tr>
      <th scope="row">{label}</th>
      <td>{said || <span className="muted">not given</span>}</td>
      <td>{actual || <span className="muted">none</span>}</td>
    </tr>
  )
}

function RequestCard({ request: r, onDone }: { request: RecoveryRequestRow; onDone: () => void }) {
  const { session } = useAdminSession()
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [problem, setProblem] = useState<string | null>(null)
  const a = r.account

  const decide = async (action: 'approve' | 'reject') => {
    setBusy(true)
    setProblem(null)
    try {
      await adminSend(`recovery/${r.id}/${action}`, session.csrfToken, { note })
      onDone()
    } catch (err) {
      setProblem(err instanceof AdminApiError ? err.message : 'Something went wrong.')
      setBusy(false)
    }
  }

  return (
    <section className="card stack" aria-label={`Request ${r.id} for ${r.username}`}>
      <p>
        <strong>{r.username}</strong> · {new Date(r.createdAt).toLocaleString()} · <span className="badge">{r.status}</span>
      </p>
      {!a ? (
        <p className="field__error">No account has this username. Reject it.</p>
      ) : (
        <>
          <p>
            Account: <Link to={`/admin/users/u/${a.userId}`}>{a.username}</Link>
            {!a.active && <span className="badge badge--warn">Disabled</span>}
            {a.hasRecoveryNumber && <span className="badge">Has a recovery number</span>}
          </p>
          <div className="table-scroll">
            <table className="admin-table">
              <thead>
                <tr>
                  <th scope="col" />
                  <th scope="col">Player says</th>
                  <th scope="col">Account has</th>
                </tr>
              </thead>
              <tbody>
                <Compare label="Nickname" said={r.answers.nickname} actual={a.nickname} />
                <Compare label="Joined" said={r.answers.joined} actual={a.joined} />
                <Compare
                  label="Friend"
                  said={r.answers.friend}
                  actual={a.friends.map((f) => (f.tag ? `${f.nickname} #${f.tag}` : f.nickname)).join(', ')}
                />
                <Compare
                  label="Games"
                  said={r.answers.games}
                  actual={a.games.map((g) => `${g.name} (${g.played})`).join(', ')}
                />
              </tbody>
            </table>
          </div>
          {r.answers.note && <p>Note from the player: {r.answers.note}</p>}
          <p>Code goes to: {r.phone}</p>
        </>
      )}
      {r.status === 'pending' ? (
        <div className="stack">
          <label className="field">
            <span className="field__label">Note (kept in the audit log)</span>
            <input className="field__input" value={note} maxLength={200} onChange={(e) => setNote(e.target.value)} />
          </label>
          <div className="admin-filters">
            {a && (
              <Button onClick={() => void decide('approve')} disabled={busy}>
                Approve and text code
              </Button>
            )}
            <Button variant="danger" onClick={() => void decide('reject')} disabled={busy}>
              Reject
            </Button>
          </div>
          {problem && (
            <p className="field__error" role="alert">
              {problem}
            </p>
          )}
        </div>
      ) : (
        <p className="muted">
          {r.reviewedBy ? `${r.status} by ${r.reviewedBy}` : r.status}
          {r.reviewNote ? `: ${r.reviewNote}` : ''}
        </p>
      )}
    </section>
  )
}
