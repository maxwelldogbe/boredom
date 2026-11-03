import { LoadState } from '../../components'
import { fmtDateTime } from '../../format'
import { MoneyGate } from '../../money/components'
import { useAdminSession } from '../../session'
import { useAdminData } from '../../useAdminData'

interface Entry {
  id: number
  at: string
  staff: string
  model: string | null
  objectId: string | null
  object: string
  message: string
}

export default function AuditPage() {
  return (
    <MoneyGate>
      <Audit />
    </MoneyGate>
  )
}

function Audit() {
  const { session } = useAdminSession()
  const { data, error, loading } = useAdminData<{ entries: Entry[] }>('money/audit')
  return (
    <div className="stack">
      <h1>Money audit</h1>
      <p className="muted">The latest staff actions on money and ID records.</p>
      {!data && <LoadState error={error} loading={loading} />}
      {data && data.entries.length === 0 && <p className="muted">Nothing yet.</p>}
      {data && data.entries.length > 0 && (
        <div className="table-scroll">
          <table className="admin-table">
            <thead>
              <tr>
                <th scope="col">When</th>
                <th scope="col">Staff</th>
                <th scope="col">Record</th>
                <th scope="col">Action</th>
              </tr>
            </thead>
            <tbody>
              {data.entries.map((e) => (
                <tr key={e.id}>
                  <td>{fmtDateTime(e.at, session.timeZone)}</td>
                  <td>{e.staff}</td>
                  <td>
                    {e.model} {e.object}
                  </td>
                  <td>{e.message}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
