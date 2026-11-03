/** Nemesis panel on a user's page: verification and wallet (by permission), lift a permanent break. */
import { Button } from '../../components/Button'
import { adminSend } from '../api'
import { LoadState } from '../components'
import { fmtDateTime } from '../format'
import { useAdminSession } from '../session'
import { useAdminData } from '../useAdminData'
import { Dl, ErrorText } from './components'
import { fmtMoney } from './format'
import type { UserMoney } from './types'
import { useMoneyAction } from './useMoneyAction'

export function UserMoneyPanel({ userId }: { userId: number }) {
  const { session } = useAdminSession()
  const { data, error, loading, reload } = useAdminData<UserMoney>(`money/users/${userId}`)
  const { act, busy, error: actError } = useMoneyAction()
  if (!session.money?.verified) return null

  const lift = async () => {
    if (await act(() => adminSend(`money/users/${userId}/remove-exclusion`, session.csrfToken))) reload()
  }
  const rows: Array<[string, string]> = []
  if (data?.verification) rows.push(['Age verification', data.verification.idState])
  if (data?.wallet) {
    const ex = data.wallet.exclusion
    rows.push(
      ['Nemesis', data.wallet.active ? 'on' : 'off'],
      ['Balance', fmtMoney(data.wallet.balance)],
      ['Held for withdrawals', fmtMoney(data.wallet.held)],
      ['Break', ex.permanent ? 'permanent' : ex.active ? `until ${fmtDateTime(ex.until, session.timeZone)}` : 'none'],
    )
  }
  return (
    <section className="card stack" aria-labelledby="user-money">
      <h2 id="user-money">Nemesis</h2>
      {!data && <LoadState error={error} loading={loading} />}
      {data && (rows.length ? <Dl rows={rows} /> : <p className="muted">You don't have permission to see this player's money.</p>)}
      {data?.canRemoveExclusion && data.wallet?.exclusion.permanent && (
        <Button variant="secondary" disabled={busy} onClick={() => void lift()}>
          Remove permanent exclusion
        </Button>
      )}
      <ErrorText message={actError} />
    </section>
  )
}
