import { act, fireEvent, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { FakeWebSocket } from '../../test/fakeWebSocket'
import { dotsFx, type ViewFixture } from '../../test/fixtures'
import { renderWithRoom } from '../../test/render'
import { SEAT_COLORS } from '../../lib/seatColors'
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

  it("someone else's turn: no line buttons and no turn text", () => {
    const fx = dotsFx.othersTurn
    const { container } = renderWithRoom(<DotsGame {...props(fx)} />)
    expect(screen.queryAllByRole('button', { name: /line, row/ })).toHaveLength(0)
    expect(container.textContent).not.toMatch(/turn/i)
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

describe('Dots and Boxes board', () => {
  it('lines are black (drawn solid, free dashed) and corner dots stay grey on top', () => {
    const fx = dotsFx.boxClosedGoAgain
    const { container } = renderWithRoom(<DotsGame {...props(fx)} />)
    const drawn = [...container.querySelectorAll('.dots__line--drawn')]
    expect(drawn).toHaveLength(Object.keys(fx.push.view.lines).length)
    for (const line of drawn) {
      expect(line.getAttribute('stroke')).toBe('#000000')
      expect(line.getAttribute('stroke-width')).toBe('8')
      expect(line.getAttribute('stroke-linecap')).toBe('butt')
      expect(line.getAttribute('stroke-dasharray')).toBeNull()
    }
    const free = [...container.querySelectorAll('.dots__line:not(.dots__line--drawn)')]
    expect(free.length).toBeGreaterThan(0)
    for (const line of free) {
      expect(line.getAttribute('stroke')).toBe('#000000')
      expect(line.getAttribute('stroke-dasharray')).toBe('4 6')
    }
    expect(container.querySelector('.dots__casing')).toBeNull()
    const dots = [...container.querySelectorAll('.dots__dot')]
    expect(dots).toHaveLength((fx.push.view.size + 1) ** 2)
    for (const dot of dots) {
      expect(dot.getAttribute('fill')).toBe('#A3A3A3')
      expect(dot.getAttribute('fill-opacity')).toBeNull()
      expect(dot.getAttribute('r')).toBe('5')
    }
    expect(container.querySelector('.dots__board')?.getAttribute('style')).toContain('background: rgb(255, 255, 255)')
  })
})

type DotsProps = ReturnType<typeof props<typeof dotsFx.done>>

/** The done fixture reseated for n players (2-4); every box is owned round-robin by seat. */
function withPlayers(n: number, me?: string): DotsProps {
  const base = props(dotsFx.done)
  const players = Array.from({ length: n }, (_, i) => ({ ...base.room.players[i % base.room.players.length], id: `p${i + 1}`, nickname: ['Ann', 'Bob', 'Cat', 'Dan'][i] }))
  const order = players.map((pl) => pl.id)
  const boxes = base.view.boxes.map((row, r) => row.map((_, c) => order[(r * row.length + c) % n]))
  const scores = Object.fromEntries(order.map((id) => [id, 1]))
  return {
    ...base,
    me: me ?? order[0],
    room: { ...base.room, players },
    view: { ...base.view, order, boxes, scores, lines: {}, lastMove: null, currentPlayerId: order[0] },
  }
}

const cards = () => within(screen.getByRole('list', { name: 'Players and boxes' })).getAllByRole('listitem')
const ring = (card: HTMLElement) => card.querySelector('.player-card__ring') as HTMLElement
const hex = (rgb: string) => '#' + (rgb.match(/\d+/g) ?? []).slice(0, 3).map((n) => Number(n).toString(16).padStart(2, '0').toUpperCase()).join('')

describe('Dots and Boxes claimed boxes', () => {
  it.each([2, 3, 4])('%i players: white box, plain initial in the owner colour', (n) => {
    const p = withPlayers(n)
    const { container } = renderWithRoom(<DotsGame {...p} />)
    expect(container.querySelector('.dots__board')?.getAttribute('style')).toContain('background: rgb(255, 255, 255)')
    const boxes = screen.getAllByLabelText(/^Box owned by/)
    expect(boxes).toHaveLength(p.view.size ** 2)
    for (const box of boxes) {
      expect(box.querySelectorAll('rect, path, polygon')).toHaveLength(0)
      expect(box.getAttribute('fill')).toBeNull()
    }
    const seen = new Set<string>()
    p.view.boxes.flat().forEach((owner, i) => {
      const text = boxes[i].querySelector('text')!
      expect(text.getAttribute('fill')).toBe(SEAT_COLORS[p.view.order.indexOf(owner!)])
      expect(text.getAttribute('fill-opacity')).toBe('1')
      expect(text.getAttribute('stroke')).toBeNull()
      expect(text.getAttribute('stroke-width')).toBeNull()
      expect(text.getAttribute('paint-order')).toBeNull()
      expect(text).toHaveClass('dots__initial')
      seen.add(text.getAttribute('fill')!)
    })
    expect([...seen].sort()).toEqual(SEAT_COLORS.slice(0, n).sort())
  })
})

describe('Dots and Boxes player cards', () => {
  it('cards follow turn order; colours follow the room seat, not the turn order', () => {
    const p = withPlayers(3)
    const order = [...p.view.order].reverse()
    const { container } = renderWithRoom(<DotsGame {...p} view={{ ...p.view, order, currentPlayerId: order[0] }} />)
    expect(cards().map((c) => c.querySelector('.player-card__name')?.firstChild?.textContent)).toEqual(['Cat', 'Bob', 'Ann'])
    expect(hex(cards()[0].style.background)).toBe(SEAT_COLORS[2])
    expect(hex(ring(cards()[1]).style.borderColor)).toBe(SEAT_COLORS[1])
    const owners = p.view.boxes.flat()
    const fills = [...container.querySelectorAll('.dots__initial')].map((t) => t.getAttribute('fill'))
    expect(fills).toEqual(owners.map((o) => SEAT_COLORS[p.room.players.findIndex((pl) => pl.id === o)]))
  })

  it('the active card follows the turn and shows the box count', () => {
    const p = withPlayers(3)
    const { rerender } = renderWithRoom(<DotsGame {...p} />)
    expect(cards()[0]).toHaveClass('player-card--active')
    expect(within(cards()[0]).getByLabelText('1 boxes')).toHaveTextContent('1')
    rerender(<DotsGame {...p} view={{ ...p.view, currentPlayerId: p.view.order[2] }} />)
    expect(cards().map((c) => c.classList.contains('player-card--active'))).toEqual([false, false, true])
  })

  it.each([2, 3, 4])('%i players: two clients agree on colours', (n) => {
    const a = withPlayers(n, 'p1')
    const b = withPlayers(n, `p${n}`)
    const colorsOf = (pp: DotsProps) => {
      const { container, unmount } = renderWithRoom(<DotsGame {...pp} />)
      const out = {
        rings: cards().map((c) => (c.classList.contains('player-card--active') ? c.style.background : ring(c).style.borderColor)),
        letters: [...container.querySelectorAll('.dots__initial')].map((t) => t.getAttribute('fill')),
      }
      unmount()
      return out
    }
    const ca = colorsOf(a)
    expect(colorsOf(b)).toEqual(ca)
    expect(new Set(ca.rings.map(hex)).size).toBe(n)
  })

  it('never renders turn text', () => {
    for (const fx of Object.values(dotsFx)) {
      const { container, unmount } = renderWithRoom(<DotsGame {...props(fx)} />)
      expect(container.textContent).not.toMatch(/turn/i)
      unmount()
    }
  })
})
