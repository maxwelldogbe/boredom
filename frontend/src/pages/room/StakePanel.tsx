import { useEffect, useState } from 'react'
import { Button } from '../../components/Button'
import { fetchBrag, getAuthToken } from '../../lib/account'
import { C } from '../../lib/constants'
import { friendlyError } from '../../lib/errors'
import { useRoomActions } from '../../state/context'
import type { RoomPublic } from '../../types/protocol'

/** Brag coin stake in the lobby (PROTOCOL.md 17): the host sets it, each player joins or sits
 *  out, and the game is staked once a majority joins. Play money only. */
export function StakePanel({ room, me }: { room: RoomPublic; me: string }) {
  const { setStake, stakeChoice, toast } = useRoomActions()
  const [balance, setBalance] = useState<number | null>(null)
  const [busy, setBusy] = useState(false)
  const self = room.players.find((p) => p.id === me)
  const registered = self?.type === 'registered'
  const isHost = room.hostId === me
  const stake = room.stake ?? 0
  const seated = room.players.length
  const joined = room.players.filter((p) => p.stakeChoice === 'in').length
  const needed = Math.floor(seated / 2) + 1

  useEffect(() => {
    const token = registered ? getAuthToken() : null
    if (!token) return
    let live = true
    fetchBrag(token)
      .then((w) => live && setBalance(w.balance))
      .catch(() => {})
    return () => {
      live = false
    }
  }, [registered, stake])

  const run = async (work: () => Promise<void>) => {
    setBusy(true)
    try {
      await work()
    } catch (err) {
      toast(friendlyError(err), 'error')
    } finally {
      setBusy(false)
    }
  }

  if (!registered && !stake) return null

  return (
    <section className="card stack stake" aria-labelledby="stake-title">
      <h2 id="stake-title" className="section-title">
        Brag coin stake
      </h2>
      {isHost && registered && (
        <div className="solo__chips" role="radiogroup" aria-label="Stake per player">
          {[0, ...C.BRAG_STAKES].map((amount) => (
            <button
              key={amount}
              type="button"
              role="radio"
              aria-checked={stake === amount}
              className={`solo__chip${stake === amount ? ' solo__chip--on' : ''}`}
              disabled={busy}
              onClick={() => void run(() => setStake(amount))}
            >
              {amount ? amount : 'None'}
            </button>
          ))}
        </div>
      )}
      {!stake ? (
        <p className="muted">No stake this round. {isHost ? 'Pick an amount to play for Brag coins.' : ''}</p>
      ) : (
        <>
          <p>
            <strong>{stake} Brag coins</strong> each. The winner takes the whole pot.
          </p>
          <p className="muted" role="status">
            {joined} of {seated} joined. {joined >= needed ? 'The stake is on.' : `${needed} must join for the stake to count.`}
          </p>
          {!registered ? (
            <p className="muted">Guests sit staked rounds out. Create a free account to play for Brag coins.</p>
          ) : (
            <>
              {balance !== null && <p className="muted">You have {balance.toLocaleString()} Brag coins.</p>}
              {!isHost && (
                <div className="stake__choice">
                  <Button
                    variant={self?.stakeChoice === 'in' ? 'primary' : 'secondary'}
                    aria-pressed={self?.stakeChoice === 'in'}
                    disabled={busy}
                    onClick={() => void run(() => stakeChoice(true))}
                  >
                    Join
                  </Button>
                  <Button
                    variant="secondary"
                    aria-pressed={self?.stakeChoice === 'out'}
                    disabled={busy}
                    onClick={() => void run(() => stakeChoice(false))}
                  >
                    Sit this round out
                  </Button>
                </div>
              )}
            </>
          )}
        </>
      )}
    </section>
  )
}
