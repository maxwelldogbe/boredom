import { act, fireEvent, screen, within } from '@testing-library/react'
import { readFileSync } from 'node:fs'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { AppRoutes } from '../../App'
import { ToastHost } from '../../components/ToastHost'
import { adoptSession } from '../../lib/account'
import { clearMemoryStorage } from '../../lib/storage'
import { fakeFetch } from '../../test/fakeFetch'
import { FakeWebSocket } from '../../test/fakeWebSocket'
import { profileFx, soloFx, type SoloSnap } from '../../test/fixtures'
import { renderWithRoom, saveTestProfile } from '../../test/render'
import type { RoomPublic } from '../../types/protocol'

let api: ReturnType<typeof fakeFetch>

beforeEach(() => {
  FakeWebSocket.reset()
  api = fakeFetch()
})
afterEach(() => {
  vi.unstubAllGlobals()
  localStorage.clear()
  clearMemoryStorage()
})

const signIn = () => adoptSession({ token: 'jwt-1', profile: profileFx.me.profile, stats: profileFx.me.stats })
const meOf = (room: RoomPublic) => room.players.find((p) => !p.bot)!.id
const app = (route: string) =>
  renderWithRoom(
    <>
      <AppRoutes />
      <ToastHost />
    </>,
    { route },
  )

/** /room/:code of a solo snapshot: rejoined by token, then the snapshot's view arrives. */
async function openRoom(snap: SoloSnap | SoloSnap<'connect_four'>) {
  signIn()
  const { room } = snap
  localStorage.setItem('partypack.roomTokens', JSON.stringify({ [room.code]: 'tok' }))
  const r = app(`/room/${room.code}`)
  const join = r.ws.frames().find((f) => f.type === 'room:join')!
  await act(async () => r.ws.ack({ playerId: meOf(room), roomToken: 'tok', room }, join.id))
  act(() => r.ws.receive({ type: 'game:view', data: snap.push }))
  return r
}

describe('home', () => {
  it('guests see a locked tile that opens the sign-up card', () => {
    saveTestProfile()
    app('/')
    const tile = screen.getByRole('button', { name: /Play alone/ })
    expect(tile).toHaveTextContent('🔒')
    fireEvent.click(tile)
    const card = screen.getByRole('dialog')
    expect(card).toHaveTextContent('Solo games are for registered players. Create a free account.')
    fireEvent.click(within(card).getByRole('button', { name: 'Sign in' }))
    expect(screen.getByRole('heading', { level: 1, name: 'Your profile' })).toBeInTheDocument()
  })

  it('guests never reach /solo; registered players get a link under Create and Join', () => {
    saveTestProfile()
    app('/solo')
    expect(screen.queryByRole('heading', { name: 'Play alone' })).not.toBeInTheDocument()
    expect(screen.queryByText('vs Bot')).not.toBeInTheDocument()
    document.body.innerHTML = ''
    FakeWebSocket.reset()
    signIn()
    app('/')
    const buttons = screen.getAllByRole('button').map((b) => b.textContent)
    expect(buttons.slice(0, 2)).toEqual(['Create room', 'Join room'])
    expect(screen.getByRole('link', { name: /Play alone/ })).toHaveAttribute('href', '/solo')
  })
})

describe('/solo picker', () => {
  it('shows the bot games; instructions open once per game, before Start', () => {
    signIn()
    const { ws } = app('/solo')
    const tiles = screen.getAllByText('vs Bot')
    expect(tiles).toHaveLength(4)
    fireEvent.click(screen.getByRole('button', { name: /Tic-Tac-Toe/ }))
    const howTo = screen.getByRole('dialog')
    expect(howTo).toHaveTextContent('You are playing against a Bot (Medium).')
    fireEvent.click(within(howTo).getByRole('button', { name: 'Continue' }))
    const sheet = screen.getByRole('dialog', { name: 'Tic-Tac-Toe' })
    expect(sheet.parentElement).toHaveClass('modal--sheet')
    expect(within(sheet).getByRole('radio', { name: 'Medium' })).toHaveAttribute('aria-checked', 'true')
    expect(ws.frames().some((f) => f.type === 'solo:start')).toBe(false)
    fireEvent.keyDown(document, { key: 'Escape' })
    fireEvent.click(screen.getByRole('button', { name: /Tic-Tac-Toe/ }))
    expect(screen.getByRole('dialog', { name: 'Tic-Tac-Toe' })).toBeInTheDocument() // no instructions again
    fireEvent.click(screen.getByRole('button', { name: 'How to play' }))
    expect(screen.getByRole('dialog')).toHaveTextContent('You are playing against a Bot')
  })

  it('Start sends solo:start with the remembered difficulty and opens the room', async () => {
    signIn()
    localStorage.setItem('partypack.soloHowToSeen', JSON.stringify(['connect_four']))
    const { ws } = app('/solo')
    fireEvent.click(screen.getByRole('button', { name: /Connect Four/ }))
    fireEvent.click(screen.getByRole('radio', { name: 'Hard' }))
    expect(localStorage.getItem('partypack.soloDifficulty')).toBe('hard')
    fireEvent.click(screen.getByRole('button', { name: 'Start' }))
    const frame = ws.lastFrame()
    expect(frame.type).toBe('solo:start')
    expect(frame.payload).toEqual({ gameId: 'connect_four', variant: { difficulty: 'hard' }, authToken: 'jwt-1' })
    await act(async () => ws.ack(soloFx.startAck, frame.id))
    expect(screen.queryByRole('heading', { name: 'Play alone' })).not.toBeInTheDocument()
    expect(JSON.parse(localStorage.getItem('partypack.roomTokens')!)).toHaveProperty(soloFx.startAck.code)
  })
})

describe('solo game screen', () => {
  it('hides the room code, score, reactions, ready, series and spectator pieces', async () => {
    const { room } = soloFx.tttMyTurn
    await openRoom(soloFx.tttMyTurn)
    expect(screen.getByRole('group', { name: 'Board' })).toBeInTheDocument()
    expect(screen.queryByText(room.code)).not.toBeInTheDocument()
    expect(screen.queryByText(/Score:/)).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /react/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Ready/ })).not.toBeInTheDocument()
    expect(screen.queryByText(/Game 1 of/)).not.toBeInTheDocument()
    expect(screen.queryByText(/Watching/)).not.toBeInTheDocument()
    expect(screen.queryByText(/Round 1/)).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Forfeit/ })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'How to play' })).toBeInTheDocument()
  })

  it('labels the bot with its difficulty and shows when it is thinking', async () => {
    const { ws } = await openRoom(soloFx.tttMyTurn)
    const cards = screen.getByRole('list', { name: 'Match players' })
    expect(cards).toHaveTextContent('Bot (Medium)')
    expect(cards.querySelector('svg.bot-icon')).not.toBeNull()
    expect(cards.querySelector('img')?.getAttribute('src') ?? '').not.toMatch(/dicebear.*Bot/)
    expect(screen.queryByText('Bot is thinking…')).not.toBeInTheDocument()
    act(() => ws.receive({ type: 'game:view', data: soloFx.tttBotTurn.push }))
    expect(screen.getByText('Bot is thinking…')).toBeInTheDocument()
  })

  it('Quit asks once, then sends solo:quit and goes back to /solo', async () => {
    const { ws } = await openRoom(soloFx.c4Playing)
    fireEvent.click(screen.getByRole('button', { name: 'Quit' }))
    const confirm = screen.getByRole('dialog', { name: 'Quit this game? Nothing is lost.' })
    fireEvent.click(within(confirm).getByRole('button', { name: 'Quit' }))
    const frame = ws.lastFrame()
    expect(frame.type).toBe('solo:quit')
    await act(async () => ws.ack({}, frame.id))
    expect(screen.getByRole('heading', { name: 'Play alone' })).toBeInTheDocument()
  })
})

describe('solo end screen', () => {
  it.each([
    ['win', 'You win!'],
    ['lose', 'You lose'],
    ['draw', 'Draw'],
  ] as const)('%s: banner, record line and the three buttons', async (outcome, banner) => {
    const snap = soloFx.tttFinished[outcome]
    const { ws } = await openRoom(snap)
    const record = snap.push.view.soloResult!.record!
    const difficulty = snap.room.soloVariant!.difficulty!
    const label = difficulty[0].toUpperCase() + difficulty.slice(1)
    expect(screen.getByRole('heading', { name: banner })).toBeInTheDocument()
    expect(
      screen.getByText(
        `Your record on ${label}: played ${record.plays}, won ${record.wins}, lost ${record.losses}, drew ${record.draws}`,
      ),
    ).toBeInTheDocument()
    expect(screen.queryByText(/points|place|rank/i)).not.toBeInTheDocument()
    for (const name of ['Play again', 'Change difficulty', 'Back']) {
      expect(screen.getByRole('button', { name })).toBeInTheDocument()
    }
    fireEvent.click(screen.getByRole('button', { name: 'Play again' }))
    expect(ws.lastFrame().type).toBe('solo:again')
  })

  it('Change difficulty quits and reopens the sheet of the same game', async () => {
    localStorage.setItem('partypack.soloHowToSeen', JSON.stringify(['tic_tac_toe']))
    const { ws } = await openRoom(soloFx.tttFinished.win)
    fireEvent.click(screen.getByRole('button', { name: 'Change difficulty' }))
    expect(ws.lastFrame().type).toBe('solo:quit')
    await act(async () => ws.ack({}, ws.lastFrame().id))
    expect(screen.getByRole('dialog', { name: 'Tic-Tac-Toe' })).toBeInTheDocument()
  })
})

describe('profile', () => {
  async function openProfile(records: unknown) {
    signIn()
    api.reply(200, profileFx.me)
    api.route('/api/solo/records', 200, records)
    app('/profile')
    await screen.findByRole('heading', { level: 1, name: profileFx.me.profile.nickname })
    return screen.findByRole('heading', { name: 'Solo records' })
  }

  it('lists played and won per game and difficulty', async () => {
    const heading = await openProfile(soloFx.records)
    const section = heading.parentElement!
    await within(section).findByText(/Tic-Tac-Toe \(Medium\)/)
    const medium = soloFx.records.find((r) => r.variant === 'medium')!
    expect(section).toHaveTextContent(`${medium.plays} played`)
    expect(section).toHaveTextContent(`${medium.wins} won`)
    expect(section).toHaveTextContent('Tic-Tac-Toe (Hard)')
  })

  it('has an empty state', async () => {
    const heading = await openProfile([])
    expect(await within(heading.parentElement!).findByText('Play alone to start your records')).toBeInTheDocument()
  })
})

describe('layout', () => {
  it('320px: chips shrink and wrap, controls are tap height, nothing has a fixed width', () => {
    const css = readFileSync('src/styles/pages.css', 'utf8')
    const solo = css.slice(css.indexOf('/* ----- solo games'))
    const rule = (name: string) => solo.match(new RegExp(`\\.${name} \\{([^}]*)\\}`))![1]
    expect(rule('solo__chips')).toMatch(/flex-wrap: wrap/)
    expect(rule('solo__chip')).toMatch(/min-width: 0/)
    expect(rule('solo__chip')).toMatch(/min-height: 44px/)
    expect(solo).not.toMatch(/overflow-x/)
    for (const [, body] of solo.matchAll(/\{([^}]*)\}/g)) expect(body).not.toMatch(/(^|\s)width: \d{3,}px/)
  })
})
