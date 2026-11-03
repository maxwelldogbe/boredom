import { useEffect, useState } from 'react'
import { Button } from '../../../components/Button'
import { adminBlob, adminSend } from '../../api'
import { LoadState } from '../../components'
import { fmtDateTime } from '../../format'
import { Dl, ErrorText, Field, MoneyGate, PersonText, StatusFilter } from '../../money/components'
import { ID_TYPES, fmtAge } from '../../money/format'
import { useStepUp } from '../../money/stepUpContext'
import type { IdRow } from '../../money/types'
import { useMoneyAction } from '../../money/useMoneyAction'
import { useAdminSession } from '../../session'
import { useAdminData } from '../../useAdminData'

const STATUSES: Array<[string, string]> = [
  ['pending', 'Pending'],
  ['approved', 'Approved'],
  ['rejected', 'Rejected'],
  ['rejected_final', 'Final'],
  ['all', 'All'],
]

export default function IdsPage() {
  return (
    <MoneyGate permission="review_ids">
      <Ids />
    </MoneyGate>
  )
}

function Ids() {
  const { session } = useAdminSession()
  const [status, setStatus] = useState('pending')
  const [openId, setOpenId] = useState<number | null>(null)
  const { data, error, loading, reload } = useAdminData<{ ids: IdRow[] }>('ids', { status })

  return (
    <div className="stack">
      <h1>ID review</h1>
      <StatusFilter value={status} options={STATUSES} onChange={setStatus} />
      {!data && <LoadState error={error} loading={loading} />}
      {data && data.ids.length === 0 && <p className="muted">Nothing to review.</p>}
      {data && data.ids.length > 0 && (
        <div className="table-scroll">
          <table className="admin-table">
            <thead>
              <tr>
                <th scope="col">Player</th>
                <th scope="col">ID</th>
                <th scope="col">Attempt</th>
                <th scope="col">Status</th>
                <th scope="col">Age</th>
                <th scope="col">
                  <span className="visually-hidden">Action</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {data.ids.map((v) => (
                <tr key={v.id}>
                  <td>
                    <PersonText person={v.user} />
                  </td>
                  <td>
                    {ID_TYPES[v.idType] ?? v.idType} ···{v.last4}
                    {v.flaggedDuplicate && <span className="badge badge--warn">duplicate</span>}
                  </td>
                  <td>{v.attemptNumber}</td>
                  <td>{v.status}</td>
                  <td>{fmtAge(v.ageSeconds)}</td>
                  <td>
                    <Button variant="secondary" onClick={() => setOpenId(v.id)} aria-label={`Open ID ${v.id}`}>
                      Open
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {openId !== null && <IdDetail key={openId} id={openId} timeZone={session.timeZone} onDone={reload} />}
    </div>
  )
}

function IdDetail({ id, timeZone, onDone }: { id: number; timeZone: string; onDone: () => void }) {
  const { session } = useAdminSession()
  const { data, error: loadError, loading, reload } = useAdminData<IdRow>(`ids/${id}`)
  const { act, busy, error, fields } = useMoneyAction()
  const [dob, setDob] = useState('')
  const [reason, setReason] = useState('')

  if (!data) return <LoadState error={loadError} loading={loading} />
  const post = async (action: string, body: unknown) => {
    if (await act(() => adminSend(`ids/${id}/${action}`, session.csrfToken, body))) {
      reload()
      onDone()
    }
  }
  return (
    <section className="card stack" aria-labelledby="id-detail">
      <h2 id="id-detail">ID {data.id}</h2>
      <Dl
        rows={[
          ['Player', <PersonText key="p" person={data.user} />],
          ['Type', ID_TYPES[data.idType] ?? data.idType],
          ['Name', data.fullName || '—'],
          ['Number ends', data.last4 || '—'],
          ['Attempt', String(data.attemptNumber)],
          ['Submitted', fmtDateTime(data.createdAt, timeZone)],
          ['Status', data.status],
          ...(data.rejectionReason ? ([['Reason', data.rejectionReason]] as Array<[string, string]>) : []),
        ]}
      />
      {data.flaggedDuplicate && <p className="money-notice">This ID number is already approved for another account.</p>}
      {data.imagesDeletedAt ? (
        <p className="muted">Photos deleted {fmtDateTime(data.imagesDeletedAt, timeZone)}.</p>
      ) : (
        <div className="id-images">
          {data.hasFront && <IdImage id={data.id} side="front" />}
          {data.hasBack && <IdImage id={data.id} side="back" />}
        </div>
      )}
      {data.status === 'pending' && (
        <div className="stack">
          <p className="muted">Check that the name and number match the photo, then type the date of birth you read on it.</p>
          <Field label="Date of birth on the ID" type="date" value={dob} onChange={(e) => setDob(e.target.value)} error={fields.dob} />
          <Button disabled={busy || !dob} onClick={() => void post('approve', { dob })}>
            Approve
          </Button>
          <Field label="Reject reason" value={reason} onChange={(e) => setReason(e.target.value)} error={fields.reason} />
          <Button variant="danger" disabled={busy || !reason.trim()} onClick={() => void post('reject', { reason })}>
            Reject
          </Button>
        </div>
      )}
      <ErrorText message={error} />
    </section>
  )
}

/** Loads one photo through the authenticated staff endpoint (with step-up) into a blob: URL. */
function IdImage({ id, side }: { id: number; side: 'front' | 'back' }) {
  const { run } = useStepUp()
  const [src, setSrc] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(
    () => () => {
      if (src) URL.revokeObjectURL(src)
    },
    [src],
  )

  const show = async () => {
    setBusy(true)
    setError(null)
    try {
      const blob = await run(() => adminBlob(`ids/${id}/image/${side}`))
      setSrc(URL.createObjectURL(blob))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load the photo.')
    } finally {
      setBusy(false)
    }
  }

  if (src) return <img className="id-image" src={src} alt={`ID ${side}`} />
  return (
    <div className="stack">
      <Button variant="secondary" onClick={() => void show()} disabled={busy}>
        {busy ? 'Loading…' : `Show ${side} photo`}
      </Button>
      <ErrorText message={error} />
    </div>
  )
}
