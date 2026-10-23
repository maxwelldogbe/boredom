import { useState } from 'react'
import { Button } from '../../components/Button'
import { PlayerChip } from '../../components/PlayerChip'
import { TimerBar } from '../../components/TimerBar'
import { C } from '../../lib/constants'
import { nameOf, playerById } from '../../lib/players'
import type { RoomPublic } from '../../types/protocol'
import type { DiceReveal, LiarsDiceView } from '../../types/views'
import type { GameUiProps } from '../types'
import { beats, bidText } from './bids'
import { Die, HiddenDie } from './Die'
import './liarsDice.css'

const FACES = [1, 2, 3, 4, 5, 6]

/** Liar's Dice (plan section 11). Only your own dice are in the view, except during a reveal. */
export function LiarsDiceGame({ view, send, me, room }: GameUiProps<LiarsDiceView>) {
  const out = (view.diceCounts[me] ?? 0) === 0
  return (
    <div className="stack dice-game">
      <div className="dice-game__header">
        <span>Round {view.round}</span>
        <span className="muted">
          {view.totalDice} dice in play{view.settings.wildOnes ? ' · ones are wild' : ''}
        </span>
      </div>

      <Table view={view} me={me} room={room} />

      {view.phase === 'reveal' && view.lastReveal && <RevealPanel reveal={view.lastReveal} view={view} me={me} room={room} />}

      {view.phase === 'bidding' && (
        <>
          <p className="dice-game__turn" role="status">
            {view.isYourTurn ? 'Your turn' : `${nameOf(room, view.currentPlayerId, me)}'s turn`}
            {view.currentBid && (
              <>
                {' · current bid '}
                <strong>{bidText(view.currentBid)}</strong> by {nameOf(room, view.currentBid.playerId, me)}
              </>
            )}
          </p>
          <TimerBar deadline={view.deadline} totalMs={C.DICE_TURN_MS} label="Turn time left" />
        </>
      )}

      {!out && view.phase !== 'done' && (
        <section className="stack dice-game__mine" aria-label="Your dice">
          <h2 className="dice-game__title">Your dice</h2>
          <div className="dice-row">
            {view.myDice.map((d, i) => (
              <Die key={i} face={d} />
            ))}
          </div>
        </section>
      )}
      {out && view.phase !== 'done' && <p className="notice">You're out of dice. Watch the others finish!</p>}

      {view.phase === 'bidding' && view.isYourTurn && (
        <BidPicker key={view.history.length} view={view} send={send} />
      )}

      {view.phase === 'bidding' && view.history.length > 0 && (
        <section aria-label="Bids this round">
          <h2 className="dice-game__title">Bids this round</h2>
          <ol className="dice-history">
            {[...view.history].reverse().map((h, i) => (
              <li key={view.history.length - i}>
                {nameOf(room, h.playerId, me)}: <strong>{bidText(h)}</strong>
                {h.auto && <span className="muted"> (time ran out)</span>}
              </li>
            ))}
          </ol>
        </section>
      )}

      {view.phase === 'done' && <p className="dice-game__turn">Game over! Results coming up…</p>}
    </div>
  )
}

function Table({ view, me, room }: { view: LiarsDiceView; me: string; room: RoomPublic }) {
  return (
    <ul className="dice-table" aria-label="Players">
      {view.order.map((pid) => {
        const count = view.diceCounts[pid] ?? 0
        return (
          <li
            key={pid}
            className={`dice-table__row${count === 0 ? ' dice-table__row--out' : ''}${pid === view.currentPlayerId ? ' dice-table__row--turn' : ''}`}
          >
            <PlayerChip player={playerById(room, pid)} isMe={pid === me} size="sm" />
            <span className="dice-table__dice" aria-label={count === 0 ? 'out' : `${count} dice`}>
              {count === 0 ? '✖ out' : Array.from({ length: count }, (_, i) => <HiddenDie key={i} />)}
            </span>
          </li>
        )
      })}
    </ul>
  )
}

function BidPicker({ view, send }: Pick<GameUiProps<LiarsDiceView>, 'view' | 'send'>) {
  const bid = view.currentBid
  const [quantity, setQuantity] = useState(() => (bid ? (bid.face < 6 ? bid.quantity : bid.quantity + 1) : 1))
  const [face, setFace] = useState<number | null>(null)
  const [sending, setSending] = useState(false)
  const minQuantity = bid ? bid.quantity : 1
  const canRaise = beats(view.totalDice, 6, bid)

  const run = async (action: Parameters<typeof send>[0]) => {
    setSending(true)
    const ok = await send(action)
    if (!ok) setSending(false)
  }

  return (
    <section className="stack dice-picker" aria-label="Your move">
      {canRaise && (
        <>
          <div className="dice-picker__qty">
            <Button variant="secondary" aria-label="Fewer dice" disabled={quantity <= minQuantity} onClick={() => setQuantity((q) => q - 1)}>
              −
            </Button>
            <span className="dice-picker__count" aria-live="polite">
              {quantity} {quantity === 1 ? 'die' : 'dice'}
            </span>
            <Button variant="secondary" aria-label="More dice" disabled={quantity >= view.totalDice} onClick={() => setQuantity((q) => q + 1)}>
              +
            </Button>
          </div>
          <div className="dice-picker__faces" role="group" aria-label="Face">
            {FACES.map((f) => {
              const ok = beats(quantity, f, bid)
              return (
                <button
                  key={f}
                  type="button"
                  className={`dice-picker__face${face === f && ok ? ' dice-picker__face--on' : ''}`}
                  disabled={!ok}
                  aria-pressed={face === f && ok}
                  aria-label={`Face ${f}`}
                  onClick={() => setFace(f)}
                >
                  <Die face={f} size="sm" />
                </button>
              )
            })}
          </div>
          <Button
            block
            disabled={sending || face === null || !beats(quantity, face, bid)}
            onClick={() => face !== null && run({ type: 'bid', quantity, face })}
          >
            {face !== null && beats(quantity, face, bid) ? `Bid ${bidText({ quantity, face })}` : 'Pick a face to bid'}
          </Button>
        </>
      )}
      {bid && (
        <div className="dice-picker__calls">
          <Button variant="danger" block disabled={sending} onClick={() => run({ type: 'callLiar' })}>
            Liar!
          </Button>
          {view.settings.spotOn && (
            <Button variant="secondary" block disabled={sending} onClick={() => run({ type: 'callSpotOn' })}>
              Spot on!
            </Button>
          )}
        </div>
      )}
    </section>
  )
}

function RevealPanel({ reveal, view, me, room }: { reveal: DiceReveal; view: LiarsDiceView; me: string; room: RoomPublic }) {
  const wild = view.settings.wildOnes && reveal.bid.face !== 1
  const hit = (d: number) => d === reveal.bid.face || (wild && d === 1)
  const name = (id: string | null) => nameOf(room, id, me)
  const caller = name(reveal.callerId)
  const callText = reveal.call === 'liar' ? 'Liar!' : 'Spot on!'
  let outcome = ''
  if (reveal.gainerId) outcome = `${name(reveal.gainerId)} ${reveal.gainerId === me ? 'gain' : 'gains'} a die.`
  if (reveal.loserId) outcome = `${name(reveal.loserId)} ${reveal.loserId === me ? 'lose' : 'loses'} a die.`
  if (reveal.eliminatedId) outcome += ` ${name(reveal.eliminatedId)} ${reveal.eliminatedId === me ? 'are' : 'is'} out!`
  return (
    <section className="stack dice-reveal" aria-label="Reveal">
      <p className="dice-reveal__headline" role="status">
        {caller} called <strong>{callText}</strong>
        {reveal.auto && ' (time ran out)'} on {bidText(reveal.bid)}.
      </p>
      <p>
        There {reveal.actual === 1 ? 'was' : 'were'} <strong>{reveal.actual}</strong>. {outcome}
      </p>
      <ul className="dice-table">
        {Object.entries(reveal.dice).map(([pid, dice]) => (
          <li key={pid} className="dice-table__row">
            <PlayerChip player={playerById(room, pid)} isMe={pid === me} size="sm" />
            <span className="dice-row dice-row--sm">
              {dice.map((d, i) => (
                <Die key={i} face={d} size="sm" highlight={hit(d)} />
              ))}
            </span>
          </li>
        ))}
      </ul>
    </section>
  )
}
