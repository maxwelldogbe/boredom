import { useState, type FormEvent } from 'react'
import { Button } from '../../../components/Button'
import { adminSend } from '../../api'
import { LoadState } from '../../components'
import { fmtDateTime } from '../../format'
import { ErrorText, Field, MoneyGate, PersonText } from '../../money/components'
import { fmtMoney, parseAmount } from '../../money/format'
import type { AdjustmentRow } from '../../money/types'
import { useMoneyAction } from '../../money/useMoneyAction'
import { useAdminSession } from '../../session'
import { useAdminData } from '../../useAdminData'

export default function AdjustmentsPage() {
  return (
    <MoneyGate permission="adjust_balances">
      <Adjustments />
    </MoneyGate>
  )
}

function Adjustments() {
  const { session } = useAdminSession()
  const { data, error, loading, reload } = useAdminData<{ adjustments: AdjustmentRow[]; dualApproval: boolean }>('money/adjustments')
  const { act, busy, error: actError, fields } = useMoneyAction()
  const [userId, setUserId] = useState('')
  const [amount, setAmount] = useState('')
  const [reason, setReason] = useState('')
  const [localError, setLocalError] = useState<string | null>(null)

  const propose = async (e: FormEvent) => {
    e.preventDefault()
    const value = parseAmount(amount, { signed: true })
    const id = Number(userId)
    if (!Number.isInteger(id) || id <= 0) return setLocalError('Enter the account id (from the user page).')
    if (value === null || value === 0) return setLocalError('Enter an amount, like 10.00 or -10.00.')
    setLocalError(null)
    if (await act(() => adminSend('money/adjustments/propose', session.csrfToken, { userId: id, amount: value, reason }))) {
      setAmount('')
      setReason('')
      reload()
    }
  }
  const decide = async (id: number, action: 'approve' | 'reject') => {
    if (await act(() => adminSend(`money/adjustments/${id}/${action}`, session.csrfToken))) reload()
  }

  return (
    <div className="stack">
      <h1>Adjustments</h1>
      <form className="card stack" onSubmit={propose} noValidate>
        <h2>Propose a correction</h2>
        <p className="muted">
          Adds new entries between the player's balance and the outside account; nothing is edited.{' '}
          {data?.dualApproval ? 'A second staff member must approve it.' : 'It applies at once.'}
        </p>
        <Field label="Account id" inputMode="numeric" value={userId} onChange={(e) => setUserId(e.target.value)} error={fields.userId} />
        <Field label="Amount (GHS, negative to take away)" inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} error={fields.amount} />
        <Field label="Reason" value={reason} onChange={(e) => setReason(e.target.value)} error={fields.reason} />
        <Button type="submit" disabled={busy || !reason.trim()}>
          Propose
        </Button>
        <ErrorText message={localError ?? actError} />
      </form>
      {!data && <LoadState error={error} loading={loading} />}
      {data && (
        <div className="table-scroll">
          <table className="admin-table">
            <thead>
              <tr>
                <th scope="col">When</th>
                <th scope="col">Player</th>
                <th scope="col" className="num">Amount</th>
                <th scope="col">Reason</th>
                <th scope="col">Status</th>
                <th scope="col">By</th>
                <th scope="col">
                  <span className="visually-hidden">Action</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {data.adjustments.map((a) => (
                <tr key={a.id}>
                  <td>{fmtDateTime(a.createdAt, session.timeZone)}</td>
                  <td>
                    <PersonText person={a.user} />
                  </td>
                  <td className="num">{fmtMoney(a.amount)}</td>
                  <td>{a.reason}</td>
                  <td>{a.status}</td>
                  <td>
                    {a.proposedBy ?? '—'}
                    {a.approvedBy && a.approvedBy !== a.proposedBy ? `, ${a.approvedBy}` : ''}
                  </td>
                  <td>
                    {a.status === 'pending' && a.proposedBy !== session.username && (
                      <span className="actions">
                        <Button variant="secondary" disabled={busy} onClick={() => void decide(a.id, 'approve')}>
                          Approve
                        </Button>
                        <Button variant="danger" disabled={busy} onClick={() => void decide(a.id, 'reject')}>
                          Reject
                        </Button>
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
