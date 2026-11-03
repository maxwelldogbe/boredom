import { gameUi } from '../../games/registry'
import type { BragWallet } from '../../lib/account'
import { LoadError } from './ProfileSections'
import type { Load } from './useLoad'

const KIND_LABELS: Record<string, string> = {
  starter: 'Welcome gift',
  bot_win: 'Beat the Hard bot',
  stake: 'Stake',
  pot_win: 'Won the pot',
  stake_refund: 'Stake returned',
}

/** Brag coins: play money won against the Hard bot (never bought, cashed out or sent). */
export function BragSection({ wallet, onRetry }: { wallet: Load<BragWallet>; onRetry: () => void }) {
  return (
    <section className="stack" aria-labelledby="brag-heading">
      <h2 id="brag-heading">Brag coins</h2>
      {wallet.status === 'loading' && <p className="muted">Loading your Brag coins…</p>}
      {wallet.status === 'error' && <LoadError message={wallet.message} onRetry={onRetry} />}
      {wallet.status === 'ready' && (
        <>
          <p className="brag__balance">{wallet.data.balance.toLocaleString()} Brag coins</p>
          <p className="muted">
            Beat any bot on Hard to win more: {wallet.data.earnedToday} of {wallet.data.dailyCap} earned today. Brag coins
            are just for fun: they can't be bought or cashed out.
          </p>
          {wallet.data.history.length > 0 && (
            <ul className="bygame" aria-label="Recent Brag coins">
              {wallet.data.history.map((e, i) => (
                <li key={`${e.at}-${i}`} className="bygame__row">
                  <span className="bygame__name">
                    {KIND_LABELS[e.kind] ?? e.kind}
                    {e.gameId ? ` · ${gameUi(e.gameId as never)?.name ?? e.gameId}` : ''}
                  </span>
                  <span className="bygame__nums">
                    <span>{e.amount > 0 ? `+${e.amount}` : e.amount}</span>
                  </span>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </section>
  )
}
