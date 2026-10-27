import { act, fireEvent, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { AppRoutes } from '../App'
import { ToastHost } from '../components/ToastHost'
import { adoptSession } from '../lib/account'
import { C } from '../lib/constants'
import { createProfile, getProfile, importProfile, resetProfile, saveProfile } from '../lib/profileStore'
import { clearMemoryStorage } from '../lib/storage'
import { fakeFetch } from '../test/fakeFetch'
import { FakeWebSocket } from '../test/fakeWebSocket'
import { profileFx, roomFx } from '../test/fixtures'
import { renderWithRoom, saveTestProfile } from '../test/render'
import type { RoomPublic } from '../types/protocol'

const SERVER_NOW = 1_793_000_000_000 // far from this clock: only differences count
const LOBBY: RoomPublic = { ...roomFx.roomFinished, status: 'lobby', selectedGame: 'rps' }
const ME = LOBBY.hostId
const OTHER = LOBBY.players.find((p) => p.id !== ME)!

beforeEach(() => {
  FakeWebSocket.reset()
  fakeFetch()
})
afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
  localStorage.clear()
  clearMemoryStorage()
})

async function settle() {
  await act(async () => {
    for (let i = 0; i < 4; i++) await Promise.resolve()
  })
}

async function app(route = '/') {
  const view = renderWithRoom(
    <>
      <AppRoutes />
      <ToastHost />
    </>,
    { route },
  )
  await settle()
  return view.ws
}

const quota = (remaining: number, lockedInMs: number | null = null) => ({
  remaining,
  limit: C.GUEST_FREE_GAMES,
  lockedUntil: lockedInMs === null ? null : SERVER_NOW + lockedInMs,
  serverNow: SERVER_NOW,
})

async function answerQuota(ws: FakeWebSocket, data: ReturnType<typeof quota>) {
  const frame = ws.frames().filter((f) => f.type === 'guest:quota').at(-1)!
  act(() => ws.ack(data, frame.id))
  await settle()
}

async function intoLobby(ws: FakeWebSocket, room: RoomPublic = LOBBY) {
  await answerQuota(ws, quota(C.GUEST_FREE_GAMES))
  fireEvent.click(screen.getByRole('button', { name: 'Create room' }))
  await settle()
  ws.ack({ playerId: ME, roomToken: 'tok', room }, ws.frames().find((f) => f.type === 'room:create')!.id)
  await settle()
}

const wall = () => screen.queryByRole('region', { name: `You've used your ${C.GUEST_FREE_GAMES} games` })

describe('lock wall', () => {
  it('Home: locked guests get the wall, buttons disabled, until the countdown ends', async () => {
    vi.useFakeTimers({ toFake: ['Date', 'setTimeout', 'clearTimeout', 'setInterval'] })
    saveTestProfile()
    const ws = await app('/')
    expect(ws.frames().find((f) => f.type === 'guest:quota')?.payload).toEqual({ profile: { id: getProfile()!.id } })
    await answerQuota(ws, quota(0, 65 * 60_000))
    const shown = wall()!
    expect(shown).toHaveTextContent('Create a free account to keep playing. It takes a minute.')
    expect(shown).toHaveTextContent('Games come back in 1h 5m')
    expect(screen.getByRole('button', { name: 'Create free account' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /close|later|dismiss/i })).toBeNull()
    expect(screen.getByRole('button', { name: 'Create room' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Join room' })).toBeDisabled()
    act(() => vi.advanceTimersByTime(60 * 60_000))
    expect(wall()).toHaveTextContent('Games come back in 0h 5m')
    act(() => vi.advanceTimersByTime(5 * 60_000 + 100))
    expect(wall()).toBeNull()
    expect(screen.getByRole('button', { name: 'Create room' })).toBeEnabled()
  })

  it('Create free account goes to signup and returns here', async () => {
    saveTestProfile()
    const ws = await app('/join/ABCD')
    await answerQuota(ws, quota(0, 60_000))
    fireEvent.click(screen.getByRole('button', { name: 'Create free account' }))
    await settle()
    expect(screen.getByRole('tab', { name: 'Create account', selected: true })).toBeInTheDocument()
  })

  it('a GUEST_LIMIT error on join shows the wall', async () => {
    saveTestProfile()
    const ws = await app('/join/ABCD')
    await answerQuota(ws, quota(1))
    act(() => ws.ack({ exists: true, hostNickname: 'Ann', playerCount: 1, status: 'lobby' }, ws.frames().find((f) => f.type === 'room:peek')!.id))
    await settle()
    const join = ws.frames().find((f) => f.type === 'room:join')!
    act(() =>
      ws.receive({ type: 'ack', id: join.id, ok: false, error: { code: 'GUEST_LIMIT', message: 'No.', data: { lockedUntil: SERVER_NOW + 60_000 } } }),
    )
    await settle()
    await answerQuota(ws, quota(0, 60_000))
    expect(wall()).toBeInTheDocument()
  })

  it('unlocked guests see no wall', async () => {
    saveTestProfile()
    const ws = await app('/')
    await answerQuota(ws, quota(5))
    expect(wall()).toBeNull()
    expect(screen.getByRole('button', { name: 'Create room' })).toBeEnabled()
  })

  it('registered players never ask and see nothing, even if pushed', async () => {
    adoptSession({ token: 'jwt-1', profile: profileFx.me.profile, stats: profileFx.me.stats })
    const ws = await app('/')
    act(() => ws.receive({ type: 'guest:quota', data: quota(0, 60_000) }))
    expect(ws.frames().map((f) => f.type)).not.toContain('guest:quota')
    expect(wall()).toBeNull()
    expect(screen.queryByText(/Games left|games come back/i)).toBeNull()
  })
})

describe('in a room', () => {
  it('counter shows at GUEST_QUOTA_SHOW_AT or fewer, and the last-game line on results', async () => {
    saveTestProfile()
    const ws = await app('/')
    await intoLobby(ws)
    act(() => ws.receive({ type: 'guest:quota', data: quota(C.GUEST_QUOTA_SHOW_AT + 1) }))
    expect(screen.queryByText(/Games left/)).toBeNull()
    act(() => ws.receive({ type: 'guest:quota', data: quota(C.GUEST_QUOTA_SHOW_AT) }))
    expect(screen.getByText(`Games left: ${C.GUEST_QUOTA_SHOW_AT}`)).toBeInTheDocument()
    act(() => ws.receive({ type: 'guest:quota', data: quota(0) }))
    act(() => ws.receive({ type: 'room:state', data: { ...LOBBY, status: 'finished' } }))
    expect(screen.getByText('That was your last game for now.')).toBeInTheDocument()
  })

  it('host: locked players are labelled, and GUEST_LIMIT on start explains who and keeps the room', async () => {
    saveTestProfile()
    const ws = await app('/')
    await intoLobby(ws)
    const withLocked = { ...LOBBY, players: LOBBY.players.map((p) => ({ ...p, locked: p.id === OTHER.id })) }
    act(() => ws.receive({ type: 'room:state', data: withLocked }))
    expect(screen.getByText('Games used')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Start game' }))
    const confirm = screen.queryByRole('button', { name: 'Start anyway' }) // the ready check asks first
    if (confirm) fireEvent.click(confirm)
    const frame = ws.frames().filter((f) => f.type === 'game:start').at(-1)!
    act(() =>
      ws.receive({
        type: 'ack',
        id: frame.id,
        ok: false,
        error: { code: 'GUEST_LIMIT', message: 'No.', data: { nicknames: [OTHER.nickname] } },
      }),
    )
    await settle()
    expect(screen.getByRole('alert')).toHaveTextContent(
      `${OTHER.nickname} can't play right now. They need an account, or wait until more players join.`,
    )
    expect(screen.getByText('Room code')).toBeInTheDocument()
    expect(wall()).toBeNull()
  })

  it('a locked player left out of the game sees the wall on the waiting screen', async () => {
    saveTestProfile()
    const ws = await app('/')
    await intoLobby(ws)
    const playing = {
      ...LOBBY,
      status: 'playing',
      players: LOBBY.players.map((p) => ({ ...p, inGame: p.id !== ME, locked: p.id === ME })),
    }
    act(() => ws.receive({ type: 'room:state', data: playing }))
    act(() => ws.receive({ type: 'guest:quota', data: quota(0, 60_000) }))
    expect(wall()).toBeInTheDocument()
  })
})

describe('profile id', () => {
  it('reset and import keep the guest id', () => {
    const guest = saveTestProfile('Sam')
    resetProfile()
    expect(getProfile()).toBeNull()
    const again = createProfile({ nickname: 'Sam', color: '#E74C3C' })
    expect(again.id).toBe(guest.id)
    saveProfile(again)
    const file = JSON.stringify({ ...again, id: 'someone-else', nickname: 'Pat' })
    const imported = importProfile(file, again.id)
    expect(imported.ok && imported.profile).toMatchObject({ id: guest.id, nickname: 'Pat' })
  })
})
