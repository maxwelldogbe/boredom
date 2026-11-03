/** History: the ledger lines (paged) and the deposit and withdrawal requests. */
import { useState } from 'react'
import { Button } from '../../../components/Button'
import { fetchDeposits, fetchEntries, fetchWithdrawals, localTime, nemesisMessage, type LedgerLine, type Wallet } from '../../../lib/nemesis'
import { WITHDRAWAL_STATUS, useMoney, useNemesisLoad } from './hooks'
import { BackButton, FormError, Loaded } from './shared'

const KIND: Record<LedgerLine['kind'], string> = {
  deposit: 'Deposit',
  withdrawal_hold: 'Withdrawal requested',
  withdrawal_paid: 'Withdrawal paid out',
  withdrawal_refund: 'Withdrawal returned',
  adjustment: 'Correction',
}

const DEPOSIT_STATUS: Record<string, string> = {
  awaiting_payment: 'Waiting for your payment',
  pending_review: 'Being checked',
  approved: 'Approved',
  rejected: 'Not approved',
  expired: 'Expired',
  cancelled: 'Cancelled',
}

export function History({ wallet, onBack }: { wallet: Wallet; onBack: () => void }) {
  const money = useMoney(wallet)
  const [entries, retryEntries] = useNemesisLoad(() => fetchEntries())
  const [more, setMore] = useState<{ lines: LedgerLine[]; cursor: number | null } | null>(null)
  const [moreError, setMoreError] = useState<string | null>(null)
  const [deposits, retryDeposits] = useNemesisLoad(fetchDeposits)
  const [withdrawals, retryWithdrawals] = useNemesisLoad(fetchWithdrawals)

  return (
    <div className="stack">
      <BackButton onBack={onBack} />
      <h3>History</h3>
      <h4>Transactions</h4>
      <Loaded load={entries} label="Loading transactions" onRetry={retryEntries}>
        {(first) => {
          const lines = [...first.entries, ...(more?.lines ?? [])]
          const cursor = more ? more.cursor : first.nextCursor
          if (!lines.length) return <p className="muted">No transactions yet.</p>
          return (
            <>
              <ul className="nemesis__list">
                {lines.map((line) => (
                  <li key={line.id} className="nemesis__row">
                    <span>
                      {KIND[line.kind] ?? line.kind}
                      {line.account === 'held' ? ' (held)' : ''}
                    </span>
                    <strong className={line.amount < 0 ? 'nemesis__out' : 'nemesis__in'}>
                      {line.amount > 0 ? '+' : ''}
                      {money(line.amount)}
                    </strong>
                    <span className="muted">{localTime(line.createdAt)}</span>
                  </li>
                ))}
              </ul>
              {cursor && (
                <Button
                  variant="secondary"
                  block
                  onClick={async () => {
                    try {
                      const page = await fetchEntries(cursor)
                      setMore({ lines: [...(more?.lines ?? []), ...page.entries], cursor: page.nextCursor })
                      setMoreError(null)
                    } catch (err) {
                      setMoreError(nemesisMessage(err))
                    }
                  }}
                >
                  Load more
                </Button>
              )}
              <FormError message={moreError} />
            </>
          )
        }}
      </Loaded>
      <h4>Deposits</h4>
      <Loaded load={deposits} label="Loading deposits" onRetry={retryDeposits}>
        {(data) =>
          data.deposits.length ? (
            <ul className="nemesis__list">
              {data.deposits.map((d) => (
                <li key={d.id} className="nemesis__row">
                  <span>
                    <strong>{money(d.amountReceived ?? d.amount)}</strong> · {DEPOSIT_STATUS[d.status] ?? d.status}
                  </span>
                  <span className="muted">
                    {d.reference} · {localTime(d.createdAt)}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted">No deposits yet.</p>
          )
        }
      </Loaded>
      <h4>Withdrawals</h4>
      <Loaded load={withdrawals} label="Loading withdrawals" onRetry={retryWithdrawals}>
        {(data) =>
          data.withdrawals.length ? (
            <ul className="nemesis__list">
              {data.withdrawals.map((w) => (
                <li key={w.id} className="nemesis__row">
                  <span>
                    <strong>{money(w.amount)}</strong> · {WITHDRAWAL_STATUS[w.status] ?? w.status}
                  </span>
                  <span className="muted">
                    {w.payoutReference ? `Reference ${w.payoutReference} · ` : ''}
                    {localTime(w.createdAt)}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted">No withdrawals yet.</p>
          )
        }
      </Loaded>
    </div>
  )
}
