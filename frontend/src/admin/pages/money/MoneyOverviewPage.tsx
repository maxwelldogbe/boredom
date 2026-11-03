import { Link, useSearchParams } from 'react-router-dom'
import { LoadState, RangeFilter, Refreshing, StatTile } from '../../components'
import { fmtDateTime } from '../../format'
import { MoneyGate } from '../../money/components'
import { fmtMoney } from '../../money/format'
import type { MoneyOverview } from '../../money/types'
import { useAdminSession } from '../../session'
import { useAdminData } from '../../useAdminData'

const WARNINGS: Record<string, string> = {
  report_stale: 'No reconciliation report in the last 24 hours.',
  report_short: 'The last reconciliation was short: the real balance is below what players are owed.',
  ledger_mismatch: 'The ledger check failed. Do not approve money actions until it is fixed.',
}

export default function MoneyOverviewPage() {
  return (
    <MoneyGate>
      <Overview />
    </MoneyGate>
  )
}

function Overview() {
  const { session } = useAdminSession()
  const [params, setParams] = useSearchParams()
  const range = params.get('range') ?? '7d'
  const { data, error, loading, refreshing } = useAdminData<MoneyOverview>('money/overview', { range })

  return (
    <div className="stack">
      <h1>Money</h1>
      {!data && <LoadState error={error} loading={loading} />}
      {data && (
        <Refreshing active={refreshing}>
          <div className="stack">
            {data.warnings.length > 0 && (
              <div className="money-alert" role="alert">
                <strong>Check this now</strong>
                <ul>
                  {data.warnings.map((w) => (
                    <li key={w}>{WARNINGS[w] ?? w}</li>
                  ))}
                </ul>
              </div>
            )}
            <RangeFilter ranges={data.ranges} value={data.range.key} onChange={(r) => setParams({ range: r })} />
            <section className="stats" aria-label="Money numbers">
              <StatTile label="Owed to players" value={fmtMoney(data.liabilities)} hint="Balances, held and escrow" />
              <StatTile label="Deposits approved" value={fmtMoney(data.depositsTotal)} hint={data.range.label} />
              <StatTile label="Withdrawals paid" value={fmtMoney(data.withdrawalsTotal)} hint={data.range.label} />
              <StatTile label="Deposits to review" value={<Link to="/admin/money/deposits">{data.pending.deposits}</Link>} />
              <StatTile label="Withdrawals to handle" value={<Link to="/admin/money/withdrawals">{data.pending.withdrawals}</Link>} />
              <StatTile label="IDs to review" value={<Link to="/admin/money/ids">{data.pending.ids}</Link>} />
              <StatTile label="Adjustments waiting" value={<Link to="/admin/money/adjustments">{data.pending.adjustments}</Link>} />
              <StatTile
                label="Last reconciliation"
                value={data.latestReport ? (data.latestReport.ok ? 'OK' : 'Short') : 'None'}
                hint={data.latestReport ? fmtDateTime(data.latestReport.createdAt, session.timeZone) : undefined}
              />
            </section>
            <section className="card stack">
              <h2>Switches</h2>
              <p>
                Deposits {data.flags.depositsEnabled ? 'on' : 'off'} · Withdrawals {data.flags.withdrawalsEnabled ? 'on' : 'off'} · Staking{' '}
                {data.flags.stakingEnabled ? 'on' : 'off'} · Dual approval {data.dualApproval ? 'on' : 'off'}
              </p>
              {data.lastMerchantChange && (
                <p className="money-notice">
                  Merchant details last changed {fmtDateTime(data.lastMerchantChange, session.timeZone)}.{' '}
                  <Link to="/admin/money/settings">Review</Link>
                </p>
              )}
            </section>
          </div>
        </Refreshing>
      )}
    </div>
  )
}
