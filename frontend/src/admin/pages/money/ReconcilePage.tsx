import { useState, type FormEvent } from 'react'
import { Button } from '../../../components/Button'
import { adminSend } from '../../api'
import { LoadState } from '../../components'
import { fmtDateTime } from '../../format'
import { ErrorText, Field, MoneyGate } from '../../money/components'
import { fmtMoney, parseAmount } from '../../money/format'
import type { LedgerCheck, ReportRow } from '../../money/types'
import { useMoneyAction } from '../../money/useMoneyAction'
import { useAdminSession } from '../../session'
import { useAdminData } from '../../useAdminData'

interface State {
  latest: ReportRow | null
  history: ReportRow[]
  ledger: LedgerCheck
}

export default function ReconcilePage() {
  return (
    <MoneyGate permission="review_deposits">
      <Reconcile />
    </MoneyGate>
  )
}

function Reconcile() {
  const { session } = useAdminSession()
  const { data, error, loading, reload } = useAdminData<State>('money/reconcile')
  const { act, busy, error: actError, fields } = useMoneyAction()
  const [balance, setBalance] = useState('')
  const [localError, setLocalError] = useState<string | null>(null)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    const amount = parseAmount(balance)
    if (amount === null) return setLocalError('Enter the real balance, like 1250.00.')
    setLocalError(null)
    if (await act(() => adminSend('money/reconcile', session.csrfToken, { reportedBalance: amount }))) {
      setBalance('')
      reload()
    }
  }

  return (
    <div className="stack">
      <h1>Reconciliation</h1>
      {!data && <LoadState error={error} loading={loading} />}
      {data && (
        <>
          <section className="card stack">
            <h2>Ledger check</h2>
            {data.ledger.ok ? (
              <p>The ledger balances. Owed to players: {fmtMoney(data.ledger.liabilities)}.</p>
            ) : (
              <p className="money-alert" role="alert">
                The ledger check failed ({data.ledger.mismatchedAccounts.length} accounts differ, {data.ledger.unbalancedTransactions} unbalanced
                transactions).
              </p>
            )}
          </section>
          <form className="card stack" onSubmit={submit} noValidate>
            <h2>Enter the real balance</h2>
            <p className="muted">The combined balance of the receiving accounts right now.</p>
            <Field label="Real balance (GHS)" inputMode="decimal" value={balance} onChange={(e) => setBalance(e.target.value)} error={fields.reportedBalance} />
            <Button type="submit" disabled={busy}>
              Save report
            </Button>
            <ErrorText message={localError ?? actError} />
          </form>
          <section className="card stack">
            <h2>History</h2>
            {data.history.length === 0 ? (
              <p className="muted">No reports yet.</p>
            ) : (
              <div className="table-scroll">
                <table className="admin-table">
                  <thead>
                    <tr>
                      <th scope="col">When</th>
                      <th scope="col" className="num">Real</th>
                      <th scope="col" className="num">Owed</th>
                      <th scope="col" className="num">Difference</th>
                      <th scope="col">Result</th>
                      <th scope="col">By</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.history.map((r) => (
                      <tr key={r.id}>
                        <td>{fmtDateTime(r.createdAt, session.timeZone)}</td>
                        <td className="num">{fmtMoney(r.reportedBalance)}</td>
                        <td className="num">{fmtMoney(r.ledgerLiabilities)}</td>
                        <td className="num">{fmtMoney(r.difference)}</td>
                        <td>{r.ok ? 'OK' : <span className="badge badge--warn">short</span>}</td>
                        <td>{r.enteredBy ?? '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </>
      )}
    </div>
  )
}
