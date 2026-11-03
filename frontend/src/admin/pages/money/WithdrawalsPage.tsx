import { useState } from 'react'
import { Button } from '../../../components/Button'
import { adminSend } from '../../api'
import { LoadState } from '../../components'
import { fmtDateTime } from '../../format'
import { Dl, ErrorText, Field, MoneyGate, PersonText, StatusFilter } from '../../money/components'
import { fmtAge, fmtMoney } from '../../money/format'
import type { WithdrawalRow } from '../../money/types'
import { useMoneyAction } from '../../money/useMoneyAction'
import { useAdminSession } from '../../session'
import { useAdminData } from '../../useAdminData'

const STATUSES: Array<[string, string]> = [
  ['open', 'Pending first'],
  ['pending_review', 'Pending'],
  ['approved', 'To pay'],
  ['paid', 'Paid'],
  ['rejected', 'Rejected'],
  ['all', 'All'],
]

export default function WithdrawalsPage() {
  return (
    <MoneyGate permission="review_withdrawals">
      <Withdrawals />
    </MoneyGate>
  )
}

function Withdrawals() {
  const { session } = useAdminSession()
  const [status, setStatus] = useState('open')
  const [openId, setOpenId] = useState<number | null>(null)
  const { data, error, loading, reload } = useAdminData<{ withdrawals: WithdrawalRow[] }>('money/withdrawals', {
    status: status === 'open' ? null : status,
  })
  const selected = data?.withdrawals.find((w) => w.id === openId) ?? null

  return (
    <div className="stack">
      <h1>Withdrawals</h1>
      <StatusFilter value={status} options={STATUSES} onChange={setStatus} />
      {!data && <LoadState error={error} loading={loading} />}
      {data && data.withdrawals.length === 0 && <p className="muted">No withdrawals here.</p>}
      {data && data.withdrawals.length > 0 && (
        <div className="table-scroll">
          <table className="admin-table">
            <thead>
              <tr>
                <th scope="col">Player</th>
                <th scope="col" className="num">Amount</th>
                <th scope="col">Status</th>
                <th scope="col">Eligible</th>
                <th scope="col">Age</th>
                <th scope="col">
                  <span className="visually-hidden">Action</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {data.withdrawals.map((w) => (
                <tr key={w.id}>
                  <td>
                    <PersonText person={w.user} />
                  </td>
                  <td className="num">{fmtMoney(w.amount)}</td>
                  <td>{w.status}</td>
                  <td>{w.eligible ? 'Yes' : fmtDateTime(w.eligibleAt, session.timeZone)}</td>
                  <td>{fmtAge(w.ageSeconds)}</td>
                  <td>
                    <Button variant="secondary" onClick={() => setOpenId(w.id)} aria-label={`Open withdrawal ${w.id}`}>
                      Open
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {selected && <WithdrawalDetail key={selected.id} withdrawal={selected} timeZone={session.timeZone} onDone={reload} />}
    </div>
  )
}

function WithdrawalDetail({ withdrawal: w, timeZone, onDone }: { withdrawal: WithdrawalRow; timeZone: string; onDone: () => void }) {
  const { session } = useAdminSession()
  const { act, busy, error, fields } = useMoneyAction()
  const [reference, setReference] = useState('')
  const [reason, setReason] = useState('')
  const snap = w.payoutSnapshot
  const post = async (action: string, body: unknown = {}) => {
    if (await act(() => adminSend(`money/withdrawals/${w.id}/${action}`, session.csrfToken, body))) onDone()
  }
  const canReject = w.status === 'pending_review' || w.status === 'approved'

  return (
    <section className="card stack" aria-labelledby="withdrawal-detail">
      <h2 id="withdrawal-detail">Withdrawal {w.id}</h2>
      <Dl
        rows={[
          ['Player', <PersonText key="p" person={w.user} />],
          ['Name on ID', w.idName ?? '—'],
          ['Amount', fmtMoney(w.amount)],
          ['Pay to', `${snap.network ?? ''} ${snap.number ?? ''}`],
          ['Account name', snap.accountName ?? '—'],
          ['Eligible from', fmtDateTime(w.eligibleAt, timeZone)],
          ['Status', w.status],
          ...(w.firstApprovedBy ? ([['First approval', w.firstApprovedBy]] as Array<[string, string]>) : []),
          ...(w.payoutReference ? ([['Payout reference', w.payoutReference]] as Array<[string, string]>) : []),
          ...(w.rejectReason ? ([['Reject reason', w.rejectReason]] as Array<[string, string]>) : []),
        ]}
      />
      {snap.accountName && w.idName && snap.accountName.toLowerCase() !== w.idName.toLowerCase() && (
        <p className="money-notice">The account name differs from the name on the ID. Check before paying.</p>
      )}
      {w.own && <p className="field__error">This is your own withdrawal. Another staff member must handle it.</p>}
      {!w.own && (
        <div className="stack">
          {w.status === 'pending_review' && (
            <Button disabled={busy || !w.eligible} onClick={() => void post('approve')}>
              {w.eligible ? 'Approve' : 'Not eligible yet'}
            </Button>
          )}
          {w.status === 'approved' && (
            <>
              <Field label="Payout reference (after you paid)" value={reference} onChange={(e) => setReference(e.target.value)} error={fields.payoutReference} />
              <Button disabled={busy || !reference.trim()} onClick={() => void post('mark-paid', { payoutReference: reference })}>
                Mark paid
              </Button>
            </>
          )}
          {canReject && (
            <>
              <Field label="Reject reason (funds go back)" value={reason} onChange={(e) => setReason(e.target.value)} error={fields.reason} />
              <Button variant="danger" disabled={busy || !reason.trim()} onClick={() => void post('reject', { reason })}>
                Reject
              </Button>
            </>
          )}
        </div>
      )}
      <ErrorText message={error} />
    </section>
  )
}
