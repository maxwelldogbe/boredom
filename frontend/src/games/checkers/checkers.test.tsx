import { act, fireEvent, screen, within } from '@testing-library/react'
import { readFileSync } from 'node:fs'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { AppRoutes } from '../../App'
import { C } from '../../lib/constants'
import { clearMemoryStorage } from '../../lib/storage'
import { FakeWebSocket } from '../../test/fakeWebSocket'
import { checkersFx, roomFx, type ViewFixture } from '../../test/fixtures'
import { renderWithRoom, saveTestProfile } from '../../test/render'
import { checkersInstructions } from '../instructions/checkers'
import { CheckersGame } from './CheckersGame'

beforeEach(() => FakeWebSocket.reset())
afterEach(() => {
  localStorage.clear()
  clearMemoryStorage()
})

function props<F extends ViewFixture>(fx: F) {
  const send = vi.fn(async () => true)
  return { view: fx.push.view as F['push']['view'], me: fx.me, room: fx.room, send }
}

const square = (r: number, c: number) => screen.getByRole('button', { name: new RegExp(`^Row ${r + 1}, column ${c + 1}:`) })
const squares = () => within(screen.getByRole('group', { name: 'Board' })).getAllByRole('button')
const labelled = (text: string) => squares().filter((b) => b.getAttribute('aria-label')!.includes(text))
const at = (b: HTMLElement) => {
  const [, r, c] = b.getAttribute('aria-label')!.match(/^Row (\d), column (\d)/)!
  return [Number(r) - 1, Number(c) - 1]
}

describe('Checkers board (real backend views)', () => {
  it('renders 32 dark squares with 12 pieces a side, coloured by seat', () => {
    renderWithRoom(<CheckersGame {...props(checkersFx.myTurn)} />)
    expect(squares()).toHaveLength(32)
    expect(labelled('red piece')).toHaveLength(12)
    expect(labelled('blue piece')).toHaveLength(12)
    expect(screen.getByTestId('piece-5-0').style.background).toMatch(/rgb\(255, 0, 0\)|#FF0000/i)
    expect(screen.getByTestId('piece-0-1').style.background).toMatch(/rgb\(0, 87, 255\)|#0057FF/i)
  })

  it('tapping a piece highlights exactly its legal destinations and sends a listed move', async () => {
    const fx = checkersFx.myTurn
    const p = props(fx)
    renderWithRoom(<CheckersGame {...p} />)
    fireEvent.click(square(5, 2))
    expect(square(5, 2)).toHaveAttribute('aria-pressed', 'true')
    const listed = fx.push.view.match!.game.legalMoves!.filter((m) => m.from[0] === 5 && m.from[1] === 2).map((m) => m.to)
    expect(labelled('move here').map(at)).toEqual(listed)
    fireEvent.click(square(5, 2)) // same piece: deselect
    expect(labelled('move here')).toHaveLength(0)
    fireEvent.click(square(6, 1)) // a piece with no legal move: nothing selected
    expect(labelled('selected')).toHaveLength(0)
    fireEvent.click(square(5, 2))
    fireEvent.click(square(3, 2)) // not a destination: deselects, sends nothing
    expect(p.send).not.toHaveBeenCalled()
    fireEvent.click(square(5, 2))
    await act(async () => fireEvent.click(square(4, 3)))
    expect(p.send).toHaveBeenCalledWith({ type: 'move', from: [5, 2], to: [4, 3] })
  })

  it('mandatory capture: the capturing piece is marked and only its capture is offered', () => {
    renderWithRoom(<CheckersGame {...props(checkersFx.mustCapture)} />)
    expect(screen.getByText('You must capture')).toBeInTheDocument()
    expect(labelled('must capture').map(at)).toEqual([[4, 3]])
    fireEvent.click(square(5, 0))
    expect(labelled('selected')).toHaveLength(0)
    fireEvent.click(square(4, 3))
    expect(labelled('capture here').map(at)).toEqual([[2, 5]])
  })

  it('multi-jump: the forced piece is selected with its next jump, nothing else can be picked; kings show ♛', async () => {
    const p = props(checkersFx.multiJump)
    const { container } = renderWithRoom(<CheckersGame {...p} />)
    expect(square(4, 3)).toHaveAttribute('aria-pressed', 'true')
    expect(labelled('capture here').map(at)).toEqual([[2, 5]])
    expect(screen.getByText(/Keep jumping/)).toBeInTheDocument()
    fireEvent.click(square(7, 6))
    expect(square(4, 3)).toHaveAttribute('aria-pressed', 'true')
    expect(container.querySelectorAll('.ck__king')).toHaveLength(2)
    expect(labelled('red king')).toHaveLength(1)
    expect(labelled('last move').map(at)).toEqual([[4, 3], [6, 1]])
    await act(async () => fireEvent.click(square(2, 5)))
    expect(p.send).toHaveBeenCalledWith({ type: 'move', from: [4, 3], to: [2, 5] })
  })

  it("opponent's turn and spectators: read-only", () => {
    const fx = checkersFx.othersTurn
    const { unmount } = renderWithRoom(<CheckersGame {...props(fx)} />)
    const waitingFor = fx.room.players.find((pl) => pl.id === fx.push.view.match!.game.turn)!.nickname
    expect(screen.getByText(`Waiting for ${waitingFor}`)).toBeInTheDocument()
    expect(squares().every((b) => b.hasAttribute('disabled'))).toBe(true)
    unmount()
    renderWithRoom(<CheckersGame {...props(checkersFx.spectator)} />)
    expect(screen.getByText(/👀 Watching/)).toBeInTheDocument()
    expect(squares().every((b) => b.hasAttribute('disabled'))).toBe(true)
    expect(screen.queryByText(/Waiting for/)).not.toBeInTheDocument()
  })

  it('series line for best of 3 and the draw notice after a drawn game', () => {
    const fx = checkersFx.afterDraw
    renderWithRoom(<CheckersGame {...props(fx)} />)
    expect(screen.getByText('Game 1 of 3')).toBeInTheDocument()
    expect(screen.getByText(`Draw: no captures or man moves for ${C.CHECKERS_DRAW_PLIES} turns`)).toBeInTheDocument()
  })
})

describe('Room screen around checkers', () => {
  async function mount(fx: ViewFixture) {
    saveTestProfile()
    localStorage.setItem('partypack.roomTokens', JSON.stringify({ [fx.room.code]: 'tok' }))
    const r = renderWithRoom(<AppRoutes />, { route: `/room/${fx.room.code}` })
    await act(async () => r.ws.ack({ ...roomFx.seatAck, room: fx.room, playerId: fx.me, roomToken: 'tok' }))
    await act(async () => r.ws.receive({ type: 'game:view', data: fx.push }))
    return r
  }

  it('Forfeit for an active player, not for a spectator', async () => {
    const { unmount } = await mount(checkersFx.myTurn)
    expect(screen.getByRole('list', { name: 'Match players' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /🏳️ Forfeit/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Send a reaction' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Menu' }))
    expect(screen.getByRole('button', { name: 'How to play' })).toBeInTheDocument()
    unmount()
    FakeWebSocket.reset()
    await mount(checkersFx.spectator)
    expect(screen.queryByRole('button', { name: /Forfeit/ })).not.toBeInTheDocument()
  })
})

describe('Checkers instructions and layout', () => {
  const text = (settings: Record<string, unknown>) => JSON.stringify(checkersInstructions({ settings, constants: C, playerCount: 2 }))

  it('numbers from constants; flying kings and backward capture lines only when on', () => {
    const off = text({ bestOf: 1, flyingKings: false, backwardCapture: false })
    expect(off).toContain('Capture all enemy pieces or leave them with no moves.')
    expect(off).toContain(`You have ${C.CHECKERS_TURN_MS / 1000} seconds per turn.`)
    expect(off).toContain(`draw after ${C.CHECKERS_DRAW_PLIES} turns`)
    expect(off).toContain('Keep your back row home as long as you can.')
    expect(off).not.toContain('Flying kings')
    expect(off).not.toContain('Backward capture')
    const on = text({ bestOf: 1, flyingKings: true, backwardCapture: true })
    expect(on).toContain('Flying kings')
    expect(on).toContain('Backward capture')
  })

  it('320px: the board scales to the width, never sideways scroll', () => {
    const css = readFileSync('src/games/checkers/checkers.css', 'utf8')
    expect(css).toMatch(/grid-template-columns: repeat\(8, minmax\(0, 1fr\)\)/)
    expect(css).toMatch(/\.ck__board \{[^}]*width: 100%;/)
    expect(css).not.toMatch(/overflow-x/)
    expect(css).not.toMatch(/(?<!max-|min-)width: (3[2-9]\d|[4-9]\d\d)px/)
  })
})
