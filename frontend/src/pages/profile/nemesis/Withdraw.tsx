/** Withdraw: payout destination (password needed), amount with a confirmation, and requests. */
import { useId, useRef, useState, type FormEvent } from 'react'
import { Button } from '../../../components/Button'
import { TextInput } from '../../../components/TextInput'
import { C } from '../../../lib/constants'
import {
  NemesisError,
  cancelWithdrawal,
  createWithdrawal,
  fetchWithdrawals,
  localTime,
  nemesisMessage,
  newIdempotencyKey,
  parseMoney,
  setPayout,
  type Payout,
  type Wallet,
  type Withdrawal,
} from '../../../lib/nemesis'
import { WITHDRAWAL_STATUS, useMoney, useNemesisLoad } from './hooks'
import { BackButton, Confirm, FormError, Loaded } from './shared'

const BANK = 'Bank transfer'

export function Withdraw({ wallet, onBack, onChanged }: { wallet: Wallet; onBack: () => void; onChanged: () => void }) {
  const [payout, setPayoutState] = useState<Payout | null>(wallet.payout)
  const [editing, setEditing] = useState(!wallet.payout)
  const [load, retry, setList] = useNemesisLoad(fetchWithdrawals)

  return (
    <div className="stack">
      <BackButton onBack={onBack} />
      <h3>Withdraw</h3>
      {editing ? (
        <PayoutForm
          current={payout}
          onSaved={(p) => {
            setPayoutState(p)
            setEditing(false)
          }}
          onCancel={payout ? () => setEditing(false) : undefined}
        />
      ) : (
        payout && (
          <div className="card stack">
            <p>
              Paying to <strong>{payout.network}</strong> {payout.number} ({payout.accountName})
            </p>
            {!payout.effective && <p className="muted">These details are active from {localTime(payout.effectiveAt)}.</p>}
            <Button variant="secondary" block onClick={() => setEditing(true)}>
              Change payout details
            </Button>
          </div>
        )
      )}
      {payout && !editing && (
        <AmountForm
          wallet={wallet}
          payout={payout}
          onCreated={(w) => {
            if (load.status === 'ready') setList({ withdrawals: [w, ...load.data.withdrawals] })
            onChanged()
          }}
        />
      )}
      <h4>Your withdrawals</h4>
      <Loaded load={load} label="Loading withdrawals" onRetry={retry}>
        {(data) => (
          <WithdrawalList
            wallet={wallet}
            items={data.withdrawals}
            onCancelled={(w) => {
              setList({ withdrawals: data.withdrawals.map((x) => (x.id === w.id ? w : x)) })
              onChanged()
            }}
          />
        )}
      </Loaded>
    </div>
  )
}

function PayoutForm({ current, onSaved, onCancel }: { current: Payout | null; onSaved: (p: Payout) => void; onCancel?: () => void }) {
  const networkId = useId()
  const [network, setNetwork] = useState<string>(current?.network ?? C.PAYMENT_NETWORKS[0])
  const [number, setNumber] = useState('')
  const [accountName, setAccountName] = useState(current?.accountName ?? '')
  const [password, setPassword] = useState('')
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [formError, setFormError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    const found: Record<string, string> = {}
    if (!number.trim()) found.number = 'Enter the number.'
    if (accountName.trim().length < 2) found.accountName = 'Enter the account name.'
    if (!password) found.password = 'Enter your password.'
    setErrors(found)
    setFormError(null)
    if (Object.keys(found).length) return
    setBusy(true)
    try {
      const method = network === BANK ? 'bank' : 'mobile_money'
      const { payout } = await setPayout({ method, network, number, accountName, password })
      onSaved(payout)
    } catch (err) {
      setBusy(false)
      if (err instanceof NemesisError) setErrors(err.fields)
      setFormError(nemesisMessage(err))
    }
  }

  return (
    <form className="stack card" onSubmit={submit} noValidate>
      <h4>Where should we send your money?</h4>
      {current && (
        <p className="muted">
          For your safety, new details take effect {C.PAYOUT_CHANGE_DELAY_HOURS} hours after you change them. Requests
          you already made are not affected.
        </p>
      )}
      <div className="field">
        <label htmlFor={networkId} className="field__label">
          Network
        </label>
        <select id={networkId} className="field__input" value={network} onChange={(e) => setNetwork(e.target.value)}>
          {C.PAYMENT_NETWORKS.map((n) => (
            <option key={n} value={n}>
              {n}
            </option>
          ))}
        </select>
      </div>
      <TextInput label={network === BANK ? 'Account number' : 'Phone number'} inputMode={network === BANK ? 'text' : 'tel'} value={number} onChange={(e) => setNumber(e.target.value)} error={errors.number} />
      <TextInput label="Account name" value={accountName} onChange={(e) => setAccountName(e.target.value)} error={errors.accountName} />
      <TextInput label="Your password" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} error={errors.password} />
      <FormError message={formError} />
      <Button type="submit" block disabled={busy}>
        {busy ? 'Saving…' : 'Save payout details'}
      </Button>
      {onCancel && (
        <Button variant="secondary" block onClick={onCancel} disabled={busy}>
          Cancel
        </Button>
      )}
    </form>
  )
}

function AmountForm({ wallet, payout, onCreated }: { wallet: Wallet; payout: Payout; onCreated: (w: Withdrawal) => void }) {
  const money = useMoney(wallet)
  const [text, setText] = useState('')
  const [amount, setAmount] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const key = useRef(newIdempotencyKey())

  const review = (e: FormEvent) => {
    e.preventDefault()
    const value = parseMoney(text, wallet.minorUnit)
    if (value === null) return setError('Enter an amount, like 50 or 50.00.')
    setError(null)
    setAmount(value)
  }

  const confirm = async () => {
    if (amount === null) return
    setBusy(true)
    try {
      const created = await createWithdrawal(amount, key.current)
      key.current = newIdempotencyKey()
      setAmount(null)
      setText('')
      onCreated(created)
    } catch (err) {
      if (!(err instanceof NemesisError && err.code === 'NETWORK')) key.current = newIdempotencyKey()
      setAmount(null)
      if (err instanceof NemesisError && err.code === 'LIMIT_REACHED' && typeof err.extra.remaining === 'number')
        setError(`That's over the daily limit. You can withdraw up to ${money(err.extra.remaining)} today.`)
      else setError(err instanceof NemesisError && err.fields.amount ? err.fields.amount : nemesisMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="stack" onSubmit={review} noValidate>
      <TextInput
        label={`Amount (${wallet.currency})`}
        inputMode="decimal"
        value={text}
        onChange={(e) => {
          setText(e.target.value)
          setError(null)
        }}
        error={error}
        hint={`Available ${money(wallet.balance)}. At least ${money(wallet.limits.platform.withdrawMin)}, up to ${money(wallet.limits.platform.withdrawDailyCap)} a day.`}
      />
      <Button type="submit" block disabled={!payout.effective}>
        Withdraw
      </Button>
      {amount !== null && (
        <Confirm title="Withdraw?" confirmLabel="Withdraw" busy={busy} onConfirm={() => void confirm()} onClose={() => setAmount(null)}>
          <p>
            Send <strong>{money(amount)}</strong> to {payout.network} {payout.number}?
          </p>
        </Confirm>
      )}
    </form>
  )
}

function WithdrawalList({ wallet, items, onCancelled }: { wallet: Wallet; items: Withdrawal[]; onCancelled: (w: Withdrawal) => void }) {
  const money = useMoney(wallet)
  const [error, setError] = useState<string | null>(null)
  if (!items.length) return <p className="muted">No withdrawals yet.</p>
  return (
    <>
      <ul className="nemesis__list">
        {items.map((w) => (
          <li key={w.id} className="nemesis__row">
            <span>
              <strong>{money(w.amount)}</strong> · {WITHDRAWAL_STATUS[w.status] ?? w.status}
            </span>
            <span className="muted">
              {w.status === 'paid' && w.payoutReference
                ? `Reference ${w.payoutReference}`
                : w.status === 'rejected' && w.rejectReason
                  ? w.rejectReason
                  : localTime(w.createdAt)}
            </span>
            {w.status === 'pending_review' && (
              <Button
                variant="secondary"
                onClick={async () => {
                  try {
                    onCancelled(await cancelWithdrawal(w.id))
                  } catch (err) {
                    setError(nemesisMessage(err))
                  }
                }}
              >
                Cancel
              </Button>
            )}
          </li>
        ))}
      </ul>
      <FormError message={error} />
    </>
  )
}
