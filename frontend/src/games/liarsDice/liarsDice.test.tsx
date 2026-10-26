import { act, fireEvent, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { FakeWebSocket } from '../../test/fakeWebSocket'
import { liarsDiceFx, type ViewFixture } from '../../test/fixtures'
import { renderWithRoom } from '../../test/render'
import { beats, bidText } from './bids'
import { LiarsDiceGame } from './LiarsDiceGame'

beforeEach(() => FakeWebSocket.reset())

function props<F extends ViewFixture>(fx: F) {
  const send = vi.fn(async () => true)
  return { view: fx.push.view as F['push']['view'], me: fx.me, room: fx.room, send }
}

describe('bid helpers', () => {
  it('formats and orders bids like the server', () => {
    expect(bidText({ quantity: 1, face: 4 })).toBe('1 × 4')
    expect(bidText({ quantity: 3, face: 6 })).toBe('3 × 6s')
    const bid = { playerId: 'x', quantity: 2, face: 4 }
    expect(beats(2, 5, bid)).toBe(true)
    expect(beats(3, 1, bid)).toBe(true)
    expect(beats(2, 4, bid)).toBe(false)
    expect(beats(1, 6, bid)).toBe(false)
    expect(beats(1, 1, null)).toBe(true)
  })
})

describe('LiarsDiceGame (real backend views)', () => {
  it('opening turn: my dice shown, no Liar button, bidding sends the action', async () => {
    const fx = liarsDiceFx.myTurnOpening
    const p = props(fx)
    renderWithRoom(<LiarsDiceGame {...p} />)
    const mine = screen.getByRole('region', { name: 'Your dice' })
    expect(within(mine).getAllByRole('img')).toHaveLength(fx.push.view.myDice.length)
    expect(screen.queryByRole('button', { name: 'Liar!' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Pick a face to bid' })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: 'More dice' }))
    fireEvent.click(screen.getByRole('button', { name: 'Face 5' }))
    await act(async () => fireEvent.click(screen.getByRole('button', { name: 'Bid 2 × 5s' })))
    expect(p.send).toHaveBeenCalledWith({ type: 'bid', quantity: 2, face: 5 })
  })

  it('after a bid: lower faces at the same quantity are disabled; Liar and Spot on are offered', async () => {
    const fx = liarsDiceFx.myTurnAfterBid
    const p = props(fx)
    renderWithRoom(<LiarsDiceGame {...p} />)
    expect(screen.getByRole('button', { name: 'Face 1' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Face 2' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Face 3' })).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Spot on!' })).toBeInTheDocument()
    await act(async () => fireEvent.click(screen.getByRole('button', { name: 'Liar!' })))
    expect(p.send).toHaveBeenCalledWith({ type: 'callLiar' })
  })

  it('a maximum bid leaves only the calls', () => {
    renderWithRoom(<LiarsDiceGame {...props(liarsDiceFx.myTurnMaxBid)} />)
    expect(screen.queryByRole('group', { name: 'Face' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Liar!' })).toBeInTheDocument()
  })

  it("someone else's turn: no picker, opponents shown face down, bid history", () => {
    const fx = liarsDiceFx.othersTurn
    renderWithRoom(<LiarsDiceGame {...props(fx)} />)
    expect(screen.queryByRole('region', { name: 'Your move' })).not.toBeInTheDocument()
    const current = fx.room.players.find((pl) => pl.id === fx.push.view.currentPlayerId)!
    const active = screen.getAllByRole('listitem').filter((li) => li.classList.contains('player-card--active'))
    expect(active).toHaveLength(1)
    expect(within(active[0]).getByText(current.nickname)).toBeInTheDocument()
    expect(screen.queryByText(/turn/i)).not.toBeInTheDocument()
    expect(screen.getAllByLabelText('3 dice').length).toBe(fx.push.view.order.length)
    expect(within(screen.getByRole('region', { name: 'Bids this round' })).getAllByRole('listitem')).toHaveLength(1)
  })

  it('reveal: every hand shown, matching dice highlighted, outcome text', () => {
    const fx = liarsDiceFx.reveal
    const { container } = renderWithRoom(<LiarsDiceGame {...props(fx)} />)
    const reveal = screen.getByRole('region', { name: 'Reveal' })
    const all = Object.values(fx.push.view.lastReveal!.dice).flat()
    expect(within(reveal).getAllByRole('img')).toHaveLength(all.length)
    const r = fx.push.view.lastReveal!
    const wild = fx.push.view.settings.wildOnes && r.bid.face !== 1
    const hits = all.filter((d) => d === r.bid.face || (wild && d === 1)).length
    expect(container.querySelectorAll('.dice-reveal .die--hit')).toHaveLength(hits)
    expect(within(reveal).getByText(/loses? a die/)).toBeInTheDocument()
  })

  it('eliminated: told they are out, no dice, no picker', () => {
    renderWithRoom(<LiarsDiceGame {...props(liarsDiceFx.eliminatedWatching)} />)
    expect(screen.getByText(/You're out of dice/)).toBeInTheDocument()
    expect(screen.queryByRole('region', { name: 'Your dice' })).not.toBeInTheDocument()
  })

  it('done', () => {
    renderWithRoom(<LiarsDiceGame {...props(liarsDiceFx.done)} />)
    expect(screen.getByText(/Game over/)).toBeInTheDocument()
  })
})
