/** Add funds: amount → payment details and reference → transaction ID → waiting for review.
 *  An open request is resumed from the server, so a refresh or network error loses nothing. */
import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Button } from '../../../components/Button'
import { CopyButton } from '../../../components/CopyButton'
import { TextInput } from '../../../components/TextInput'
import {
  NemesisError,
  cancelDeposit,
  createDeposit,
  fetchDeposits,
  nemesisMessage,
  newIdempotencyKey,
  parseMoney,
  submitDeposit,
  type Deposit,
  type Wallet,
} from '../../../lib/nemesis'
import { useMoney, useNemesisLoad } from './hooks'
import { BackButton, FormError, Loaded } from './shared'

export const DEPOSIT_POLL_MS = 20_000

export function AddFunds({ wallet, onBack, onSettled }: { wallet: Wallet; onBack: () => void; onSettled: () => void }) {
  const [load, retry] = useNemesisLoad(fetchDeposits)
  const [deposit, setDeposit] = useState<Deposit | null>(null)

  return (
    <div className="stack">
      <BackButton onBack={onBack} />
      <h3>Add funds</h3>
      <Loaded load={load} label="Loading your deposit" onRetry={retry}>
        {(data) => {
          const current = deposit ?? data.open
          if (!current) return <AmountStep wallet={wallet} onCreated={setDeposit} />
          if (current.status === 'awaiting_payment')
            return <PayStep wallet={wallet} deposit={current} onChange={setDeposit} />
          return <WaitStep wallet={wallet} deposit={current} onChange={setDeposit} onDone={onSettled} />
        }}
      </Loaded>
    </div>
  )
}

function AmountStep({ wallet, onCreated }: { wallet: Wallet; onCreated: (d: Deposit) => void }) {
  const money = useMoney(wallet)
  const { platform, player } = wallet.limits
  const [text, setText] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const key = useRef(newIdempotencyKey())

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    const amount = parseMoney(text, wallet.minorUnit)
    if (amount === null) return setError('Enter an amount, like 50 or 50.00.')
    setBusy(true)
    setError(null)
    try {
      onCreated(await createDeposit(amount, key.current))
    } catch (err) {
      setBusy(false)
      if (err instanceof NemesisError && err.code === 'LIMIT_REACHED' && typeof err.extra.remaining === 'number')
        setError(`That's over your limit. You can add up to ${money(err.extra.remaining)} right now.`)
      else setError(err instanceof NemesisError && err.fields.amount ? err.fields.amount : nemesisMessage(err))
      if (!(err instanceof NemesisError && err.code === 'NETWORK')) key.current = newIdempotencyKey()
    }
  }

  return (
    <form className="stack" onSubmit={submit} noValidate>
      <TextInput
        label={`Amount (${wallet.currency})`}
        inputMode="decimal"
        value={text}
        onChange={(e) => {
          setText(e.target.value)
          setError(null)
        }}
        error={error}
        hint={`Between ${money(platform.depositMin)} and ${money(platform.depositMax)}. Your limits: ${money(player.depositDaily)} a day, ${money(player.deposit30d)} in 30 days.`}
      />
      <Button type="submit" block disabled={busy}>
        {busy ? 'Please wait…' : 'Continue'}
      </Button>
    </form>
  )
}

function PayStep({ wallet, deposit, onChange }: { wallet: Wallet; deposit: Deposit; onChange: (d: Deposit) => void }) {
  const money = useMoney(wallet)
  const details = deposit.paymentDetails
  const [paymentRef, setPaymentRef] = useState('')
  const [sender, setSender] = useState('')
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [formError, setFormError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const key = useRef(newIdempotencyKey())

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    const found: Record<string, string> = {}
    if (!paymentRef.trim()) found.paymentRef = 'Enter the transaction ID from your payment.'
    if (!sender.trim()) found.senderNumber = 'Enter the number you paid from.'
    setErrors(found)
    setFormError(null)
    if (Object.keys(found).length) return
    setBusy(true)
    try {
      onChange(await submitDeposit(deposit.id, paymentRef, sender, key.current))
    } catch (err) {
      setBusy(false)
      if (err instanceof NemesisError) setErrors(err.fields)
      setFormError(nemesisMessage(err))
    }
  }

  const cancel = async () => {
    setBusy(true)
    try {
      onChange(await cancelDeposit(deposit.id))
    } catch (err) {
      setBusy(false)
      setFormError(nemesisMessage(err))
    }
  }

  return (
    <div className="stack">
      <div className="card stack nemesis__pay">
        <p>
          Send exactly <strong>{money(deposit.amount)}</strong> to:
        </p>
        <dl className="nemesis__details">
          <dt>Network</dt>
          <dd>{details.network}</dd>
          <dt>Number</dt>
          <dd>{details.number}</dd>
          <dt>Account name</dt>
          <dd>{details.accountName}</dd>
          <dt>Reference</dt>
          <dd className="nemesis__reference">{deposit.reference}</dd>
        </dl>
        <p>
          <strong>Put this reference in the payment note.</strong>
        </p>
        <CopyButton text={deposit.reference} label="Copy reference" copiedMessage="Reference copied" />
      </div>
      <form className="stack" onSubmit={submit} noValidate>
        <p className="muted">After paying, enter the transaction ID from your confirmation message.</p>
        <TextInput label="Transaction ID" autoComplete="off" value={paymentRef} onChange={(e) => setPaymentRef(e.target.value)} error={errors.paymentRef} />
        <TextInput label="Number you paid from" type="tel" autoComplete="tel" value={sender} onChange={(e) => setSender(e.target.value)} error={errors.senderNumber} />
        <FormError message={formError} />
        <Button type="submit" block disabled={busy}>
          I've paid
        </Button>
        <Button variant="secondary" block disabled={busy} onClick={() => void cancel()}>
          Cancel deposit
        </Button>
      </form>
    </div>
  )
}

function WaitStep({ wallet, deposit, onChange, onDone }: { wallet: Wallet; deposit: Deposit; onChange: (d: Deposit) => void; onDone: () => void }) {
  const money = useMoney(wallet)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (deposit.status !== 'pending_review') return
    const timer = window.setInterval(async () => {
      try {
        const { deposits } = await fetchDeposits()
        const fresh = deposits.find((d) => d.id === deposit.id)
        setError(null)
        if (fresh && fresh.status !== deposit.status) onChange(fresh)
      } catch (err) {
        setError(nemesisMessage(err))
      }
    }, DEPOSIT_POLL_MS)
    return () => window.clearInterval(timer)
  }, [deposit, onChange])

  const outcome: Record<string, string> = {
    approved: `Approved. ${money(deposit.amountReceived ?? deposit.amount)} was added to your balance.`,
    rejected: `Not approved${deposit.rejectReason ? `: ${deposit.rejectReason}` : '.'}`,
    expired: 'This deposit expired before it was paid.',
    cancelled: 'This deposit was cancelled.',
  }
  return (
    <div className="stack" aria-live="polite">
      {deposit.status === 'pending_review' ? (
        <>
          <p>
            <strong>Waiting for confirmation</strong>
          </p>
          <p className="muted">
            We're checking your payment of {money(deposit.amount)} (reference {deposit.reference}). This page checks again
            every 20 seconds.
          </p>
        </>
      ) : (
        <>
          <p>{outcome[deposit.status]}</p>
          <Button block onClick={onDone}>
            Done
          </Button>
        </>
      )}
      <FormError message={error} />
    </div>
  )
}
