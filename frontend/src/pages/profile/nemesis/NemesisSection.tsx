/** The "Nemesis" section of /profile (registered players, only while the server enables it).
 *  Every state shows its own visible buttons; every number comes from the server. */
import { useState } from 'react'
import { Button } from '../../../components/Button'
import { Modal } from '../../../components/Modal'
import { activate, deactivate, fetchStatus, fetchWallet, nemesisMessage, type NemesisStatus, type Wallet } from '../../../lib/nemesis'
import { useRoomActions } from '../../../state/context'
import { AddFunds } from './AddFunds'
import { History } from './History'
import { IdForm } from './IdForm'
import { Limits, TakeBreak } from './Limits'
import { useMoney, useNemesisLoad } from './hooks'
import { Confirm, FormError, Loaded } from './shared'
import { Withdraw } from './Withdraw'

type Screen = 'home' | 'verify' | 'add' | 'withdraw' | 'history' | 'limits' | 'break'

export function NemesisSection() {
  const [status, retryStatus, setStatus] = useNemesisLoad(fetchStatus)
  if (status.status === 'ready' && !status.data.enabled) return null
  return (
    <section className="card stack nemesis" aria-labelledby="nemesis-heading">
      <h2 id="nemesis-heading">Nemesis</h2>
      <Loaded load={status} label="Loading Nemesis" onRetry={retryStatus}>
        {(data) => <NemesisBody status={data} onStatus={setStatus} />}
      </Loaded>
    </section>
  )
}

function NemesisBody({ status, onStatus }: { status: NemesisStatus; onStatus: (s: NemesisStatus) => void }) {
  const [screen, setScreen] = useState<Screen>('home')
  const showWallet = status.active || status.idState === 'approved'
  const home = () => setScreen('home')

  if (screen === 'verify')
    return (
      <IdForm
        retentionDays={status.retentionDays ?? 0}
        onBack={home}
        onDone={(s) => {
          onStatus(s)
          home()
        }}
      />
    )
  if (!showWallet) return <IdState status={status} onVerify={() => setScreen('verify')} />
  return <WalletArea status={status} onStatus={onStatus} screen={screen} setScreen={setScreen} />
}

function IdState({ status, onVerify }: { status: NemesisStatus; onVerify: () => void }) {
  switch (status.idState) {
    case 'pending':
      return <p role="status">We're checking your ID. This usually takes less than a day.</p>
    case 'rejected':
      return (
        <div className="stack">
          <p role="status">Your ID could not be verified{status.rejectionReason ? `: ${status.rejectionReason}` : '.'}</p>
          <Button block onClick={onVerify}>
            Try again ({status.attemptsLeft} {status.attemptsLeft === 1 ? 'try' : 'tries'} left)
          </Button>
        </div>
      )
    case 'rejected_final':
      return <p role="status">We couldn't verify your age, so Nemesis isn't available on this account.</p>
    default:
      return (
        <div className="stack">
          <p className="muted">Play friends for real money. You need to be 18 or older.</p>
          <Button block onClick={onVerify}>
            Verify your age
          </Button>
        </div>
      )
  }
}

function WalletArea({
  status,
  onStatus,
  screen,
  setScreen,
}: {
  status: NemesisStatus
  onStatus: (s: NemesisStatus) => void
  screen: Screen
  setScreen: (s: Screen) => void
}) {
  const [wallet, retryWallet] = useNemesisLoad(fetchWallet)
  const home = () => setScreen('home')
  const refresh = () => retryWallet()
  const backAndRefresh = () => {
    refresh()
    home()
  }

  if (wallet.status !== 'ready')
    return (
      <Loaded load={wallet} label="Loading your balance" onRetry={retryWallet}>
        {() => null}
      </Loaded>
    )
  const data = wallet.data
  switch (screen) {
    case 'add':
      return (
        <AddFunds
          wallet={data}
          onBack={home}
          onSettled={() => {
            refresh()
            home()
          }}
        />
      )
    case 'withdraw':
      return <Withdraw wallet={data} onBack={backAndRefresh} onChanged={() => undefined} />
    case 'history':
      return <History wallet={data} onBack={home} />
    case 'limits':
      return <Limits wallet={data} onBack={backAndRefresh} onChanged={() => undefined} />
    case 'break':
      return (
        <TakeBreak
          wallet={data}
          onBack={home}
          onChanged={() => {
            refresh()
            void fetchStatus().then(onStatus, () => undefined)
            home()
          }}
        />
      )
    default:
      return status.active ? (
        <OnHome wallet={data} onStatus={onStatus} go={setScreen} />
      ) : (
        <OffHome status={status} wallet={data} onStatus={onStatus} go={setScreen} />
      )
  }
}

function Balance({ wallet }: { wallet: Wallet }) {
  const money = useMoney(wallet)
  return (
    <div className="nemesis__balance">
      <span className="muted">Balance</span>
      <strong className="nemesis__amount">{money(wallet.balance)}</strong>
      {wallet.held > 0 && <span className="muted">{money(wallet.held)} waiting to be paid out</span>}
    </div>
  )
}

function OnHome({ wallet, onStatus, go }: { wallet: Wallet; onStatus: (s: NemesisStatus) => void; go: (s: Screen) => void }) {
  const { toast } = useRoomActions()
  const [confirmOff, setConfirmOff] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const turnOff = async () => {
    setBusy(true)
    try {
      onStatus(await deactivate())
      toast('Nemesis is off.')
    } catch (err) {
      setError(nemesisMessage(err))
      setConfirmOff(false)
      setBusy(false)
    }
  }

  return (
    <div className="stack">
      <Balance wallet={wallet} />
      {wallet.exclusion.active && <p role="status">You're on a break. Adding funds is blocked; you can still withdraw.</p>}
      <div className="nemesis__actions">
        <Button block onClick={() => go('add')}>
          Add funds
        </Button>
        <Button variant="secondary" block onClick={() => go('withdraw')}>
          Withdraw
        </Button>
        <Button variant="secondary" block onClick={() => go('history')}>
          History
        </Button>
        <Button variant="secondary" block onClick={() => go('limits')}>
          Limits
        </Button>
        <Button variant="secondary" block onClick={() => go('break')}>
          Take a break
        </Button>
        <Button variant="secondary" block onClick={() => setConfirmOff(true)}>
          Turn off
        </Button>
      </div>
      <FormError message={error} />
      {confirmOff && (
        <Confirm title="Turn off Nemesis?" confirmLabel="Turn off" busy={busy} onConfirm={() => void turnOff()} onClose={() => setConfirmOff(false)}>
          <p>Your balance and history are kept. You can still withdraw.</p>
        </Confirm>
      )}
    </div>
  )
}

function OffHome({
  status,
  wallet,
  onStatus,
  go,
}: {
  status: NemesisStatus
  wallet: Wallet
  onStatus: (s: NemesisStatus) => void
  go: (s: Screen) => void
}) {
  const [dialog, setDialog] = useState(false)
  const e = status.eligibility
  const hasMoney = wallet.balance > 0 || wallet.held > 0
  let blocked: string | null = null
  if (status.excluded) blocked = "You're on a break"
  else if (e && e.gamesNeeded > 0) blocked = `Play ${e.gamesNeeded} more ${e.gamesNeeded === 1 ? 'game' : 'games'}`
  else if (e && !e.accountAgeOk) blocked = `Available in ${e.hoursLeft} ${e.hoursLeft === 1 ? 'hour' : 'hours'}`

  return (
    <div className="stack">
      <p className="muted">Your age is verified.</p>
      {hasMoney && <Balance wallet={wallet} />}
      {blocked ? (
        <Button block disabled>
          {blocked}
        </Button>
      ) : (
        <Button block onClick={() => setDialog(true)}>
          Turn on Nemesis
        </Button>
      )}
      {hasMoney && (
        <div className="nemesis__actions">
          <Button variant="secondary" block onClick={() => go('withdraw')}>
            Withdraw
          </Button>
          <Button variant="secondary" block onClick={() => go('history')}>
            History
          </Button>
        </div>
      )}
      <Button variant="secondary" block onClick={() => go('break')}>
        Take a break
      </Button>
      {dialog && <TurnOnDialog rulesVersion={status.rulesVersion ?? 0} onClose={() => setDialog(false)} onDone={onStatus} />}
    </div>
  )
}

function TurnOnDialog({ rulesVersion, onClose, onDone }: { rulesVersion: number; onClose: () => void; onDone: (s: NemesisStatus) => void }) {
  const [adult, setAdult] = useState(false)
  const [rules, setRules] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const submit = async () => {
    setBusy(true)
    try {
      onDone(await activate(rulesVersion))
    } catch (err) {
      setError(nemesisMessage(err))
      setBusy(false)
    }
  }

  return (
    <Modal
      title="Turn on Nemesis"
      onClose={onClose}
      actions={
        <>
          <Button block disabled={!adult || !rules || busy} onClick={() => void submit()}>
            {busy ? 'Please wait…' : 'Turn on'}
          </Button>
          <Button variant="secondary" block onClick={onClose} disabled={busy} data-autofocus>
            Cancel
          </Button>
        </>
      }
    >
      <div className="stack">
        <ul className="nemesis__rules">
          <li>Nemesis uses real money.</li>
          <li>You can lose the money you stake.</li>
          <li>You can set deposit limits or take a break at any time.</li>
          <li>You can turn Nemesis off at any time and still withdraw your balance.</li>
        </ul>
        <label className="nemesis__check">
          <input type="checkbox" checked={adult} onChange={(e) => setAdult(e.target.checked)} />
          I am 18 or older
        </label>
        <label className="nemesis__check">
          <input type="checkbox" checked={rules} onChange={(e) => setRules(e.target.checked)} />
          I have read the rules
        </label>
        <FormError message={error} />
      </div>
    </Modal>
  )
}
