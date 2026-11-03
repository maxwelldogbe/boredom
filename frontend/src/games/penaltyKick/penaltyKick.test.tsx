import { act, fireEvent, screen } from '@testing-library/react'
import { readFileSync } from 'node:fs'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { AppRoutes } from '../../App'
import { C } from '../../lib/constants'
import { clearMemoryStorage } from '../../lib/storage'
import { FakeWebSocket } from '../../test/fakeWebSocket'
import { penaltyKickFx, roomFx, type ViewFixture } from '../../test/fixtures'
import { renderWithRoom, saveTestProfile } from '../../test/render'
import { penaltyKickInstructions } from '../instructions/penaltyKick'
import { diveFromSwipe, keeperPose, svgToGoal } from './geometry'
import { PenaltyKickGame } from './PenaltyKickGame'

beforeEach(() => FakeWebSocket.reset())
afterEach(() => {
  localStorage.clear()
  clearMemoryStorage()
})

type Fx = (typeof penaltyKickFx)[keyof typeof penaltyKickFx]

function setup(fx: Fx) {
  const send = vi.fn(async () => true)
  const r = renderWithRoom(<PenaltyKickGame view={fx.push.view} me={fx.me} room={fx.room} send={send} />)
  const svg = r.container.querySelector('svg.pk-scene__svg') as SVGSVGElement
  return { ...r, send, svg }
}

const game = (fx: Fx) => fx.push.view.match!.game
const nick = (fx: Fx, id: string | null) => fx.room.players.find((p) => p.id === id)!.nickname

const transformOf = (p: { dx: number; dy: number; angle: number }) => `translate(${p.dx}px, ${p.dy}px) rotate(${p.angle}deg)`

/** A swipe in client pixels (identity CTM in jsdom: client pixels are SVG units). */
function swipe(svg: SVGSVGElement, from: [number, number], to: [number, number], pointerId = 1) {
  fireEvent.pointerDown(svg, { pointerId, clientX: from[0], clientY: from[1] })
  fireEvent.pointerMove(svg, { pointerId, clientX: (from[0] + to[0]) / 2, clientY: (from[1] + to[1]) / 2 })
  fireEvent.pointerUp(svg, { pointerId, clientX: to[0], clientY: to[1] })
}

describe('Penalty kick scene (real backend views)', () => {
  it('aiming as shooter: a swipe must start at the ball; where it ends is the aim', async () => {
    const { svg, send } = setup(penaltyKickFx.aimingShooter)
    expect(screen.getByText(/Swipe from the ball to the spot you want\. A faster flick = more power/)).toBeInTheDocument()
    expect(screen.getByText('Power')).toBeVisible()
    expect(screen.getByRole('meter', { name: 'Power' })).toBeInTheDocument()
    await act(async () => swipe(svg, [195, 300], [100, 200])) // not from the ball
    expect(send).not.toHaveBeenCalled()
    await act(async () => swipe(svg, [195, 600], [200, 590])) // too short
    expect(send).not.toHaveBeenCalled()
    expect(screen.getByText('Swipe from the ball toward the goal')).toBeInTheDocument()
    await act(async () => swipe(svg, [190, 605], [100, 200]))
    expect(send).toHaveBeenCalledTimes(1)
    expect(send).toHaveBeenCalledWith({ type: 'shoot', aim: svgToGoal({ x: 100, y: 200 }), power: expect.any(Number) })
  })

  it('shows a trail and target ring while swiping, and ignores extra fingers', () => {
    const { svg, container } = setup(penaltyKickFx.aimingShooter)
    fireEvent.pointerDown(svg, { pointerId: 1, clientX: 195, clientY: 600 })
    fireEvent.pointerDown(svg, { pointerId: 2, clientX: 50, clientY: 50 })
    fireEvent.pointerMove(svg, { pointerId: 1, clientX: 120, clientY: 220 })
    expect(container.querySelector('[data-testid="pk-trail"] circle')).toBeInTheDocument()
    fireEvent.pointerCancel(svg, { pointerId: 1 })
    expect(container.querySelector('[data-testid="pk-trail"]')).toBeNull()
  })

  it('aiming as keeper: waiting for the shooter, cannot act, nothing reveals an aim', async () => {
    const fx = penaltyKickFx.aimingKeeper
    expect(JSON.stringify(fx.push)).not.toMatch(/"to"|"aim"/)
    const { svg, send, container } = setup(fx)
    expect(screen.getByText(`${nick(fx, game(fx).shooter)} is lining up the shot...`)).toBeInTheDocument()
    await act(async () => swipe(svg, [195, 600], [100, 200]))
    expect(send).not.toHaveBeenCalled()
    expect(container.querySelector('[data-testid="pk-trail"]')).toBeNull()
    expect(container.querySelector('[data-testid="pk-ball"]')).toHaveAttribute('transform', 'translate(195 600) scale(1)')
  })

  it('aiming: the keeper stands where the patrol path puts them', () => {
    const fx = penaltyKickFx.aimingKeeper
    const path = game(fx).keeperPath!
    expect(path.length).toBeGreaterThan(2)
    const { container } = setup(fx) // the test clock is long past the path: its last point
    const keeper = container.querySelector('[data-testid="pk-keeper"]') as SVGGElement
    expect(keeper.style.transform).toBe(transformOf(keeperPose(path[path.length - 1], null)))
  })

  it('flight as keeper: a swipe dives from the keeper spot at once and is sent only once', async () => {
    const fx = penaltyKickFx.flightKeeper
    const spot = game(fx).flight!.keeperSpot
    const { svg, send, container } = setup(fx)
    expect(screen.getByText('Swipe to dive before the ball arrives!')).toBeInTheDocument()
    expect(container.querySelector('.pk-react')).toBeInTheDocument()
    const keeper = container.querySelector('[data-testid="pk-keeper"]') as SVGGElement
    expect(keeper.style.transform).toBe(transformOf(keeperPose(spot, null)))
    await act(async () => swipe(svg, [200, 400], [60, 400]))
    const dive = diveFromSwipe(spot, -140, 0)
    expect(send).toHaveBeenCalledTimes(1)
    expect(send).toHaveBeenCalledWith({ type: 'dive', ...dive })
    expect(keeper.style.transform).toBe(transformOf(keeperPose(spot, dive)))
    await act(async () => swipe(svg, [200, 400], [300, 300]))
    expect(send).toHaveBeenCalledTimes(1)
  })

  it('flight as shooter: the ball leaves the spot, no outcome yet', () => {
    const fx = penaltyKickFx.flightShooter
    expect(game(fx).outcome).toBeNull()
    const { container } = setup(fx)
    expect(container.querySelector('[data-testid="pk-ball"]')).not.toHaveAttribute('transform', 'translate(195 600) scale(1)')
    expect(screen.queryByText(/GOAL!|SAVED!|WIDE!/)).not.toBeInTheDocument()
    expect(screen.queryByText(/Swipe/)).not.toBeInTheDocument()
  })

  it.each([
    ['result_goal', 'GOAL!', 'scored.'],
    ['result_saved', 'SAVED!', 'saved it.'],
    ['result_wide', 'WIDE!', 'missed.'],
    ['result_over', 'OVER!', 'missed.'],
    ['result_post', 'POST!', 'missed.'],
    ['result_fizzled', 'WEAK!', 'missed.'],
  ] as const)('result %s: banner, who, next kick and tracker', (key, banner, line) => {
    const fx = penaltyKickFx[key]
    const g = game(fx)
    const { container } = setup(fx)
    expect(container.querySelector('.pk-banner__title')).toHaveTextContent(banner)
    const who = key === 'result_saved' ? g.keeper : g.shooter
    expect(container.querySelector('.pk-banner__line')).toHaveTextContent(`${who === fx.me ? 'You' : nick(fx, who)} ${line}`)
    expect(screen.getByText(/^Next kick in \d+$/)).toBeInTheDocument()
    const dots = screen.getByRole('list', { name: 'Kicks' })
    expect(dots).toHaveTextContent(key === 'result_goal' ? '1 of 1 kick scored' : '0 of 1 kick scored')
  })

  it('spectator: everything read-only under the watch banner', async () => {
    const { svg, send } = setup(penaltyKickFx.spectator)
    expect(screen.getByText(/👀 Watching/)).toBeInTheDocument()
    await act(async () => swipe(svg, [200, 400], [60, 400]))
    expect(send).not.toHaveBeenCalled()
    expect(screen.queryByText(/Swipe/)).not.toBeInTheDocument()
  })

  it('the old tap zones and Safe/Power controls are gone', () => {
    setup(penaltyKickFx.aimingShooter)
    expect(screen.queryByRole('button', { name: /Shoot|Dive|Safe|Power|Left|Center|Right/ })).not.toBeInTheDocument()
  })

  it('done: the champion and the final tracker', () => {
    setup(penaltyKickFx.done)
    expect(screen.getByText(/🏆 You win!/)).toBeInTheDocument()
    expect(screen.getByRole('list', { name: 'Kicks' })).toHaveTextContent('2 of 2 kicks scored')
  })
})

describe('Room screen around penalty kick', () => {
  async function mount(fx: ViewFixture) {
    saveTestProfile()
    localStorage.setItem('partypack.roomTokens', JSON.stringify({ [fx.room.code]: 'tok' }))
    const r = renderWithRoom(<AppRoutes />, { route: `/room/${fx.room.code}` })
    await act(async () => r.ws.ack({ ...roomFx.seatAck, room: fx.room, playerId: fx.me, roomToken: 'tok' }))
    await act(async () => r.ws.receive({ type: 'game:view', data: fx.push }))
    return r
  }

  it('active player: cards, Forfeit, reactions and How to play; spectator: no Forfeit', async () => {
    const { unmount } = await mount(penaltyKickFx.aimingShooter)
    expect(screen.getByRole('list', { name: 'Match players' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /🏳️ Forfeit/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Send a reaction' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Menu' }))
    expect(screen.getByRole('button', { name: 'How to play' })).toBeInTheDocument()
    unmount()
    FakeWebSocket.reset()
    await mount(penaltyKickFx.spectator)
    expect(screen.getByText(/👀 Watching/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Forfeit/ })).not.toBeInTheDocument()
  })
})

describe('Penalty kick instructions and layout', () => {
  it('describe swiping, with the kicks setting and the aim time', () => {
    const text = JSON.stringify(penaltyKickInstructions({ settings: { kicksPerPlayer: 3 }, constants: C, playerCount: 2 }))
    expect(text).toContain('Score more goals than your opponent.')
    expect(text).toContain('Shooter: swipe from the ball toward the spot you want.')
    expect(text).toContain('3 kicks each, then sudden death if tied.')
    expect(text).toContain(`You have ${C.PENALTY_AIM_MS / 1000} seconds to shoot`)
    expect(text).toContain('Corners beat keepers, but hit them with a controlled flick.')
  })

  it('320px: the scene stretches to its column, nothing scrolls sideways', () => {
    const css = readFileSync('src/games/penaltyKick/penaltyKick.css', 'utf8')
    expect(css).toMatch(/\.pk-scene \{[^}]*width: 100%;[^}]*touch-action: none;/)
    expect(css).not.toMatch(/overflow-x/)
    expect(css).not.toMatch(/(?<!max-|min-)width: (3[2-9]\d|[4-9]\d\d)px/)
  })
})
