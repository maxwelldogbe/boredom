/** Deposit limits (lowering is immediate, raising waits) and taking a break. */
import { useState, type FormEvent } from 'react'
import { Button } from '../../../components/Button'
import { TextInput } from '../../../components/TextInput'
import { C } from '../../../lib/constants'
import { NemesisError, localTime, nemesisMessage, parseMoney, setLimits, takeBreak, type Wallet } from '../../../lib/nemesis'
import { useMoney } from './hooks'
import { BackButton, Confirm, FormError } from './shared'

const major = (amount: number, minorUnit: number) => String(amount / minorUnit)

export function Limits({ wallet, onBack, onChanged }: { wallet: Wallet; onBack: () => void; onChanged: () => void }) {
  const money = useMoney(wallet)
  const [limits, setLimitsState] = useState(wallet.limits)
  const [daily, setDaily] = useState(major(limits.player.depositDaily, wallet.minorUnit))
  const [thirty, setThirty] = useState(major(limits.player.deposit30d, wallet.minorUnit))
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [formError, setFormError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    const d = parseMoney(daily, wallet.minorUnit)
    const t = parseMoney(thirty, wallet.minorUnit)
    const found: Record<string, string> = {}
    if (d === null) found.depositDailyLimit = 'Enter an amount.'
    if (t === null) found.deposit30dLimit = 'Enter an amount.'
    setErrors(found)
    setFormError(null)
    if (d === null || t === null) return
    setBusy(true)
    try {
      setLimitsState(await setLimits(d, t))
      onChanged()
    } catch (err) {
      if (err instanceof NemesisError) setErrors(err.fields)
      setFormError(nemesisMessage(err))
    } finally {
      setBusy(false)
    }
  }

  const raise = limits.pendingRaise
  return (
    <form className="stack" onSubmit={submit} noValidate>
      <BackButton onBack={onBack} />
      <h3>Deposit limits</h3>
      <p>
        Now: {money(limits.player.depositDaily)} a day and {money(limits.player.deposit30d)} in 30 days.
      </p>
      {raise && (
        <p className="muted" role="status">
          Raise waiting:
          {raise.depositDailyLimit !== undefined && ` ${money(raise.depositDailyLimit)} a day`}
          {raise.deposit30dLimit !== undefined && ` ${money(raise.deposit30dLimit)} in 30 days`}, from {localTime(raise.effectiveAt)}.
        </p>
      )}
      <p className="muted">
        Lower limits apply at once. Higher limits apply after {C.LIMIT_RAISE_DELAY_HOURS} hours. The most you can set is{' '}
        {money(limits.platform.depositDaily)} a day and {money(limits.platform.deposit30d)} in 30 days.
      </p>
      <TextInput label={`Daily limit (${wallet.currency})`} inputMode="decimal" value={daily} onChange={(e) => setDaily(e.target.value)} error={errors.depositDailyLimit} />
      <TextInput label={`30-day limit (${wallet.currency})`} inputMode="decimal" value={thirty} onChange={(e) => setThirty(e.target.value)} error={errors.deposit30dLimit} />
      <FormError message={formError} />
      <Button type="submit" block disabled={busy}>
        {busy ? 'Saving…' : 'Save limits'}
      </Button>
    </form>
  )
}

type BreakChoice = 7 | 30 | 'permanent'

const BREAK_LABEL: Record<string, string> = { 7: '7 days', 30: '30 days', permanent: 'Permanently' }

export function TakeBreak({ wallet, onBack, onChanged }: { wallet: Wallet; onBack: () => void; onChanged: () => void }) {
  const [choice, setChoice] = useState<BreakChoice | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const exclusion = wallet.exclusion

  const confirm = async () => {
    if (choice === null) return
    setBusy(true)
    try {
      await takeBreak(choice)
      setChoice(null)
      onChanged()
    } catch (err) {
      setError(nemesisMessage(err))
      setChoice(null)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="stack">
      <BackButton onBack={onBack} />
      <h3>Take a break</h3>
      {exclusion.active && (
        <p role="status">
          {exclusion.permanent ? "You're on a permanent break." : `You're on a break until ${localTime(exclusion.until)}.`}
        </p>
      )}
      <p className="muted">During a break you can't add funds or turn Nemesis on. You can always withdraw.</p>
      {(C.SELF_EXCLUSION_DAYS as BreakChoice[]).map((days) => (
        <Button key={String(days)} variant={days === 'permanent' ? 'danger' : 'secondary'} block onClick={() => setChoice(days)}>
          {BREAK_LABEL[String(days)]}
        </Button>
      ))}
      <FormError message={error} />
      {choice !== null && (
        <Confirm
          title={choice === 'permanent' ? 'Take a permanent break?' : `Take a ${BREAK_LABEL[String(choice)]} break?`}
          confirmLabel="Start break"
          danger
          busy={busy}
          onConfirm={() => void confirm()}
          onClose={() => setChoice(null)}
        >
          <p>Blocked: adding funds and turning Nemesis on.</p>
          <p>Still allowed: withdrawing your balance and seeing your history.</p>
          <p>
            {choice === 'permanent'
              ? 'You cannot undo a permanent break yourself. Only our team can lift it.'
              : 'It starts now and cannot be shortened.'}
          </p>
        </Confirm>
      )}
    </div>
  )
}
