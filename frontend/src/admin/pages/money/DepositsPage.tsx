import { useState } from 'react'
import { Button } from '../../../components/Button'
import { adminSend } from '../../api'
import { LoadState } from '../../components'
import { fmtDateTime } from '../../format'
import { Dl, ErrorText, Field, MoneyGate, PersonText, StatusFilter } from '../../money/components'
import { fmtAge, fmtMoney, majorText, parseAmount } from '../../money/format'
import type { DepositRow } from '../../money/types'
import { useMoneyAction } from '../../money/useMoneyAction'
import { useAdminSession } from '../../session'
import { useAdminData } from '../../useAdminData'

const STATUSES: Array<[string, string]> = [
  ['open', 'Pending first'],
  ['pending_review', 'Pending'],
  ['approved', 'Approved'],
  ['rejected', 'Rejected'],
  ['all', 'All'],
]

export default function DepositsPage() {
  return (
    <MoneyGate permission="review_deposits">
      <Deposits />
    </MoneyGate>
  )
}

function Deposits() {
  const { session } = useAdminSession()
  const [status, setStatus] = useState('open')
  const [openId, setOpenId] = useState<number | null>(null)
  const { data, error, loading, reload } = useAdminData<{ deposits: DepositRow[]; dualApproval: boolean }>('money/deposits', {
    status: status === 'open' ? null : status,
  })
  const selected = data?.deposits.find((d) => d.id === openId) ?? null

  return (
    <div className="stack">
      <h1>Deposits</h1>
      <StatusFilter value={status} options={STATUSES} onChange={setStatus} />
      {!data && <LoadState error={error} loading={loading} />}
      {data && data.deposits.length === 0 && <p className="muted">No deposits here.</p>}
      {data && data.deposits.length > 0 && (
        <div className="table-scroll">
          <table className="admin-table">
            <thead>
              <tr>
                <th scope="col">Player</th>
                <th scope="col">Reference</th>
                <th scope="col" className="num">Requested</th>
                <th scope="col">Transaction ID</th>
                <th scope="col">Status</th>
                <th scope="col">Age</th>
                <th scope="col">
                  <span className="visually-hidden">Action</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {data.deposits.map((d) => (
                <tr key={d.id}>
                  <td>
                    <PersonText person={d.user} />
                  </td>
                  <td className="mono">{d.reference}</td>
                  <td className="num">{fmtMoney(d.amountRequested)}</td>
                  <td className="mono">{d.paymentRef ?? '—'}</td>
                  <td>{d.status}</td>
                  <td>{fmtAge(d.ageSeconds)}</td>
                  <td>
                    <Button variant="secondary" onClick={() => setOpenId(d.id)} aria-label={`Open deposit ${d.reference}`}>
                      Open
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {selected && (
        <DepositDetail
          key={selected.id}
          deposit={selected}
          timeZone={session.timeZone}
          onDone={() => {
            reload()
          }}
        />
      )}
    </div>
  )
}

function DepositDetail({ deposit, timeZone, onDone }: { deposit: DepositRow; timeZone: string; onDone: () => void }) {
  const { session } = useAdminSession()
  const { act, busy, error, fields } = useMoneyAction()
  const [verified, setVerified] = useState(false)
  const [received, setReceived] = useState(majorText(deposit.amountReceived ?? deposit.amountRequested))
  const [note, setNote] = useState('')
  const [reason, setReason] = useState('')
  const [localError, setLocalError] = useState<string | null>(null)
  const snap = deposit.merchantSnapshot
  const pending = deposit.status === 'pending_review'

  const approve = async () => {
    const amount = parseAmount(received)
    if (amount === null) return setLocalError('Enter the amount received, like 50.00.')
    setLocalError(null)
    const done = await act(() =>
      adminSend(`money/deposits/${deposit.id}/approve`, session.csrfToken, { receivedAmount: amount, verifiedInAccount: verified, note }),
    )
    if (done) onDone()
  }
  const reject = async () => {
    if (await act(() => adminSend(`money/deposits/${deposit.id}/reject`, session.csrfToken, { reason }))) onDone()
  }

  return (
    <section className="card stack" aria-labelledby="deposit-detail">
      <h2 id="deposit-detail">Deposit {deposit.reference}</h2>
      <Dl
        rows={[
          ['Player', <PersonText key="p" person={deposit.user} />],
          ['Requested', fmtMoney(deposit.amountRequested)],
          ['Received (credited)', fmtMoney(deposit.amountReceived)],
          ['Transaction ID', deposit.paymentRef ?? '—'],
          ['Sender number', deposit.senderNumber || '—'],
          ['Paid to', `${snap.network ?? ''} ${snap.number ?? ''} (${snap.accountName ?? ''})`],
          ['Submitted', fmtDateTime(deposit.submittedAt, timeZone)],
          ['Status', deposit.status],
          ...(deposit.firstApprovedBy ? ([['First approval', deposit.firstApprovedBy]] as Array<[string, string]>) : []),
          ...(deposit.rejectReason ? ([['Reject reason', deposit.rejectReason]] as Array<[string, string]>) : []),
          ...(deposit.note ? ([['Note', deposit.note]] as Array<[string, string]>) : []),
        ]}
      />
      {deposit.own && <p className="field__error">This is your own deposit. Another staff member must review it.</p>}
      {pending && !deposit.own && (
        <div className="stack">
          <label className="check">
            <input type="checkbox" checked={verified} onChange={(e) => setVerified(e.target.checked)} />I verified this payment in the
            receiving account
          </label>
          <Field label="Amount received (GHS)" inputMode="decimal" value={received} onChange={(e) => setReceived(e.target.value)} error={fields.receivedAmount} />
          <Field label="Note (needed if the amount differs)" value={note} onChange={(e) => setNote(e.target.value)} error={fields.note} />
          <Button disabled={busy || !verified} onClick={() => void approve()}>
            Approve and credit
          </Button>
          <Field label="Reject reason" value={reason} onChange={(e) => setReason(e.target.value)} error={fields.reason} />
          <Button variant="danger" disabled={busy || !reason.trim()} onClick={() => void reject()}>
            Reject
          </Button>
        </div>
      )}
      <ErrorText message={localError ?? error} />
    </section>
  )
}
