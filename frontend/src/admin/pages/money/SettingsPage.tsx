import { useState, type FormEvent } from 'react'
import { Button } from '../../../components/Button'
import { C } from '../../../lib/constants'
import { adminSend } from '../../api'
import { LoadState } from '../../components'
import { fmtDateTime } from '../../format'
import { ErrorText, Field, MoneyGate } from '../../money/components'
import type { Flags, MerchantRow } from '../../money/types'
import { useMoneyAction } from '../../money/useMoneyAction'
import { useAdminSession } from '../../session'
import { useAdminData } from '../../useAdminData'

const FLAG_LABELS: Array<[keyof Flags, string]> = [
  ['depositsEnabled', 'Deposits'],
  ['withdrawalsEnabled', 'Withdrawals'],
  ['stakingEnabled', 'Staking'],
]

export default function SettingsPage() {
  return (
    <MoneyGate>
      <div className="stack">
        <h1>Money settings</h1>
        <MerchantSection />
        <FlagsSection />
      </div>
    </MoneyGate>
  )
}

function MerchantSection() {
  const { session } = useAdminSession()
  const canEdit = session.money?.permissions.includes('edit_merchant') ?? false
  const { data, error, loading, reload } = useAdminData<{ active: MerchantRow | null; versions: MerchantRow[]; dualApproval: boolean }>('money/merchant')
  const { act, busy, error: actError, fields } = useMoneyAction()
  const [network, setNetwork] = useState<string>(C.PAYMENT_NETWORKS[0])
  const [number, setNumber] = useState('')
  const [accountName, setAccountName] = useState('')

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    const method = network === 'Bank transfer' ? 'bank' : 'mobile_money'
    if (await act(() => adminSend('money/merchant', session.csrfToken, { method, network, number, accountName }, 'PUT'))) {
      setNumber('')
      reload()
    }
  }
  const approve = async (id: number) => {
    if (await act(() => adminSend(`money/merchant/${id}/approve`, session.csrfToken))) reload()
  }

  return (
    <section className="card stack" aria-labelledby="merchant">
      <h2 id="merchant">Merchant details (where players pay)</h2>
      {!data && <LoadState error={error} loading={loading} />}
      {data && (
        <>
          {data.active ? (
            <p className="money-notice">
              Active: <strong>{data.active.network}</strong> {data.active.number} ({data.active.accountName}), since{' '}
              {fmtDateTime(data.active.activatedAt, session.timeZone)}
            </p>
          ) : (
            <p className="money-alert" role="alert">
              No active merchant details: players cannot deposit.
            </p>
          )}
          {canEdit && (
            <form className="stack" onSubmit={submit} noValidate>
              <div className="field">
                <label className="field__label" htmlFor="merchant-network">
                  Network
                </label>
                <select id="merchant-network" className="field__input" value={network} onChange={(e) => setNetwork(e.target.value)}>
                  {C.PAYMENT_NETWORKS.map((n) => (
                    <option key={n}>{n}</option>
                  ))}
                </select>
              </div>
              <Field label="Number" value={number} onChange={(e) => setNumber(e.target.value)} error={fields.number} />
              <Field label="Account name" value={accountName} onChange={(e) => setAccountName(e.target.value)} error={fields.accountName} />
              <Button type="submit" disabled={busy}>
                {data.dualApproval ? 'Propose new details' : 'Save new details'}
              </Button>
              <p className="muted small">Open deposit requests keep the details they were shown.</p>
            </form>
          )}
          <div className="table-scroll">
            <table className="admin-table">
              <caption className="visually-hidden">Version history</caption>
              <thead>
                <tr>
                  <th scope="col">Created</th>
                  <th scope="col">Details</th>
                  <th scope="col">State</th>
                  <th scope="col">By</th>
                  <th scope="col">
                    <span className="visually-hidden">Action</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {data.versions.map((m) => (
                  <tr key={m.id}>
                    <td>{fmtDateTime(m.createdAt, session.timeZone)}</td>
                    <td>
                      {m.network} {m.number} ({m.accountName})
                    </td>
                    <td>{m.active ? 'Active' : m.pending ? 'Waiting for approval' : 'Old'}</td>
                    <td>
                      {m.createdBy ?? '—'}
                      {m.approvedBy && m.approvedBy !== m.createdBy ? `, approved by ${m.approvedBy}` : ''}
                    </td>
                    <td>
                      {m.pending && canEdit && m.createdBy !== session.username && (
                        <Button variant="secondary" disabled={busy} onClick={() => void approve(m.id)}>
                          Approve
                        </Button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <ErrorText message={actError} />
        </>
      )}
    </section>
  )
}

function FlagsSection() {
  const { session } = useAdminSession()
  const canEdit = session.money?.permissions.includes('edit_flags') ?? false
  const { data, error, loading, reload } = useAdminData<{
    flags: Flags
    pending: { field: string; value: boolean; proposedBy: number } | null
    dualApproval: boolean
  }>('money/flags')
  const { act, busy, error: actError } = useMoneyAction()

  const toggle = async (field: keyof Flags, value: boolean) => {
    if (await act(() => adminSend('money/flags', session.csrfToken, { field, value }))) reload()
  }
  const approve = async () => {
    if (await act(() => adminSend('money/flags/approve', session.csrfToken))) reload()
  }

  return (
    <section className="card stack" aria-labelledby="flags">
      <h2 id="flags">Switches</h2>
      {!data && <LoadState error={error} loading={loading} />}
      {data && (
        <>
          {FLAG_LABELS.map(([field, label]) => (
            <div key={field} className="money-flag">
              <span>
                {label}: <strong>{data.flags[field] ? 'on' : 'off'}</strong>
              </span>
              {canEdit && (
                <Button variant={data.flags[field] ? 'danger' : 'secondary'} disabled={busy} onClick={() => void toggle(field, !data.flags[field])}>
                  {data.flags[field] ? `Turn ${label.toLowerCase()} off` : `Turn ${label.toLowerCase()} on`}
                </Button>
              )}
            </div>
          ))}
          {data.pending && (
            <div className="money-notice stack">
              <p>
                Waiting for a second approval: {data.pending.field} → {data.pending.value ? 'on' : 'off'}
              </p>
              {canEdit && (
                <Button disabled={busy} onClick={() => void approve()}>
                  Approve change
                </Button>
              )}
            </div>
          )}
          <ErrorText message={actError} />
        </>
      )}
    </section>
  )
}
