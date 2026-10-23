import { act, fireEvent, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { FakeWebSocket } from '../../test/fakeWebSocket'
import { dotsFx, type ViewFixture } from '../../test/fixtures'
import { renderWithRoom } from '../../test/render'
import { DotsGame } from './DotsGame'

beforeEach(() => FakeWebSocket.reset())

function props<F extends ViewFixture>(fx: F) {
  const send = vi.fn(async () => true)
  return { view: fx.push.view as F['push']['view'], me: fx.me, room: fx.room, send }
}

describe('DotsGame (real backend views)', () => {
  it('my turn: every free line is a button; tapping one draws it', async () => {
    const fx = dotsFx.myTurnStart
    const p = props(fx)
    renderWithRoom(<DotsGame {...p} />)
    expect(screen.getByText('Your turn: draw a line')).toBeInTheDocument()
    const size = fx.push.view.size
    expect(screen.getAllByRole('button', { name: /line, row/ })).toHaveLength(2 * size * (size + 1))
    await act(async () => fireEvent.click(screen.getByRole('button', { name: 'Horizontal line, row 1, column 1' })))
    expect(p.send).toHaveBeenCalledWith({ type: 'drawLine', id: 'h:0:0' })
  })

  it('keyboard Enter draws a line', async () => {
    const p = props(dotsFx.myTurnStart)
    renderWithRoom(<DotsGame {...p} />)
    await act(async () => fireEvent.keyDown(screen.getByRole('button', { name: 'Vertical line, row 1, column 1' }), { key: 'Enter' }))
    expect(p.send).toHaveBeenCalledWith({ type: 'drawLine', id: 'v:0:0' })
  })

  it("someone else's turn: no line buttons, their name in the banner", () => {
    const fx = dotsFx.othersTurn
    renderWithRoom(<DotsGame {...props(fx)} />)
    expect(screen.queryAllByRole('button', { name: /line, row/ })).toHaveLength(0)
    const current = fx.room.players.find((pl) => pl.id === fx.push.view.currentPlayerId)!
    expect(screen.getByText(`${current.nickname}'s turn`)).toBeInTheDocument()
  })

  it('closing a box shows the owner and an extra-turn note; drawn lines are not buttons', () => {
    const fx = dotsFx.boxClosedGoAgain
    renderWithRoom(<DotsGame {...props(fx)} />)
    expect(screen.getByText(/closed a box and goes again/)).toBeInTheDocument()
    expect(screen.getByLabelText('Box owned by You')).toBeInTheDocument()
    const size = fx.push.view.size
    const free = 2 * size * (size + 1) - Object.keys(fx.push.view.lines).length
    expect(screen.getAllByRole('button', { name: /line, row/ })).toHaveLength(free)
  })

  it('done: every box owned, no turn controls', () => {
    const fx = dotsFx.done
    renderWithRoom(<DotsGame {...props(fx)} />)
    expect(screen.getByText(/All boxes are claimed/)).toBeInTheDocument()
    expect(screen.queryAllByRole('button', { name: /line, row/ })).toHaveLength(0)
    expect(screen.getAllByLabelText(/^Box owned by/)).toHaveLength(fx.push.view.size ** 2)
    expect(screen.queryByRole('timer')).not.toBeInTheDocument()
  })
})
