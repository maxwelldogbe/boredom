import { act, fireEvent, screen, within } from '@testing-library/react'
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { AppRoutes } from '../../App'
import { ToastHost } from '../../components/ToastHost'
import AboutPage from '../AboutPage'
import { GAME_LIST } from '../../games/registry'
import { C } from '../../lib/constants'
import { friendlyError } from '../../lib/errors'
import { RequestError } from '../../lib/socket'
import { clearMemoryStorage } from '../../lib/storage'
import { FakeWebSocket } from '../../test/fakeWebSocket'
import { registeredOnlyFx, roomFx } from '../../test/fixtures'
import { renderWithRoom, saveTestProfile } from '../../test/render'
import { GamePicker } from './GamePicker'

beforeEach(() => FakeWebSocket.reset())
afterEach(() => {
  localStorage.clear()
  clearMemoryStorage()
})

const RO_IDS: readonly string[] = C.REGISTERED_ONLY_GAMES
const RO_NAMES = GAME_LIST.filter((g) => RO_IDS.includes(g.id)).map((g) => g.name)
const OPEN_NAMES = GAME_LIST.filter((g) => !RO_IDS.includes(g.id)).map((g) => g.name)
const cards = () => within(screen.getByRole('heading', { name: 'Pick a game' }).parentElement!).getAllByRole('button')

async function mount({ me, room }: { me: string; room: (typeof registeredOnlyFx)['hostLobby']['room'] }) {
  saveTestProfile()
  localStorage.setItem('partypack.roomTokens', JSON.stringify({ [room.code]: 'tok' }))
  const r = renderWithRoom(
    <>
      <AppRoutes />
      <ToastHost />
    </>,
    { route: `/room/${room.code}` },
  )
  const joinFrame = r.ws.frames().find((f) => f.type === 'room:join')!
  await act(async () => r.ws.ack({ ...roomFx.seatAck, room, playerId: me, roomToken: 'tok' }, joinFrame.id))
  return r
}

describe('Game picker', () => {
  it('guests see only the open games', () => {
    const { me, room } = registeredOnlyFx.guestHostEmpty
    renderWithRoom(<GamePicker room={room} me={me} />)
    const text = cards().map((c) => c.textContent).join(' ')
    for (const name of OPEN_NAMES) expect(text).toContain(name)
    for (const name of RO_NAMES) expect(text).not.toContain(name)
    expect(screen.queryByText('Registered players only')).not.toBeInTheDocument()
  })

  it('registered players see every game, with no "registered players only" label', () => {
    const { me, room } = registeredOnlyFx.registeredHostEmpty
    renderWithRoom(<GamePicker room={room} me={me} />)
    expect(cards()).toHaveLength(GAME_LIST.length)
    expect(screen.queryByText(/registered players only/i)).not.toBeInTheDocument()
  })

  it('/about names no registered-only game', () => {
    renderWithRoom(<AboutPage />)
    for (const name of RO_NAMES) expect(document.body.textContent).not.toContain(name)
  })
})

describe('Lobby around a registered-only game', () => {
  it('registered host: names the guests who sit out (up to 3, then "and N more")', async () => {
    await mount(registeredOnlyFx.hostLobby)
    expect(screen.getByText("Ann and Cat can't play this game. They'll wait while you play.")).toBeInTheDocument()
    FakeWebSocket.reset()
    document.body.innerHTML = ''
    await mount(registeredOnlyFx.hostLobbyManyGuests)
    expect(screen.getByText("Ann, Cat, Dan and 1 more can't play this game. They'll wait while you play.")).toBeInTheDocument()
  })

  it('REGISTERED_ONLY on start explains who are guests', async () => {
    const { ws } = await mount(registeredOnlyFx.hostLobby)
    fireEvent.click(screen.getByRole('button', { name: 'Start game' }))
    const confirm = screen.queryByRole('button', { name: 'Start anyway' })
    if (confirm) fireEvent.click(confirm)
    const frame = ws.frames().filter((f) => f.type === 'game:start').at(-1)!
    await act(async () =>
      ws.receive({ type: 'ack', id: frame.id, ok: false, error: { code: 'REGISTERED_ONLY', message: 'No.', data: { nicknames: ['Ann', 'Cat'] } } }),
    )
    expect(await screen.findByRole('alert')).toHaveTextContent('Not enough registered players to start. Ann and Cat are guests.')
  })

  it('blocked guest: the card, Create account back to this room, no ready button, no game name', async () => {
    const fx = registeredOnlyFx.guestLobby
    await mount(fx)
    expect(screen.getByRole('heading', { name: 'The host picked a game for registered players.' })).toBeInTheDocument()
    expect(screen.getByText('Create a free account to join in.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: "I'm ready" })).not.toBeInTheDocument()
    for (const name of RO_NAMES) expect(document.body.textContent).not.toContain(name)
    fireEvent.click(screen.getByRole('button', { name: 'Create account' }))
    expect(screen.getByRole('tab', { name: 'Create account', selected: true })).toBeInTheDocument()
  })

  it('blocked guest while the game runs (also after a refresh): card, players and Leave, no game view', async () => {
    await mount(registeredOnlyFx.guestPlaying)
    expect(screen.getByRole('heading', { name: 'The host picked a game for registered players.' })).toBeInTheDocument()
    expect(screen.getByRole('list', { name: 'Players in the room' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Leave room' })).toBeInTheDocument()
    expect(screen.queryByText(/Starting the game/)).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Forfeit/ })).not.toBeInTheDocument()
    for (const name of RO_NAMES) expect(document.body.textContent).not.toContain(name)
  })

  it('game_unselected: a toast for the new host', async () => {
    const fx = registeredOnlyFx.guestHostEmpty
    const { ws } = await mount(fx)
    await act(async () =>
      ws.receive({ type: 'room:event', data: { kind: 'game_unselected', playerId: fx.me, nickname: 'Ann', data: { reason: 'registered_only' } } }),
    )
    expect(await screen.findByText('The game was unselected because a guest became the host.')).toBeInTheDocument()
  })
})

describe('Registered-only plumbing', () => {
  it('REGISTERED_ONLY maps to a plain message', () => {
    expect(friendlyError(new RequestError('REGISTERED_ONLY', 'raw server text'))).toBe('This game is for registered players.')
  })

  it('no registered-only id is hardcoded outside the constant (game folders and types excepted)', () => {
    const skip = ['src/games', 'src/types', 'src/test']
    const files: string[] = []
    const walk = (dir: string) => {
      for (const entry of readdirSync(dir)) {
        const path = join(dir, entry)
        if (statSync(path).isDirectory()) {
          if (!skip.includes(path)) walk(path)
        } else if (/\.tsx?$/.test(entry) && !/\.test\.tsx?$/.test(entry)) files.push(path)
      }
    }
    walk('src')
    expect(files.length).toBeGreaterThan(20)
    for (const file of files) {
      const text = readFileSync(file, 'utf8')
      for (const id of RO_IDS) expect(text.includes(id), `${file} mentions ${id}`).toBe(false)
    }
  })
})
