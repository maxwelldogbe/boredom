import { act, fireEvent, screen, within } from '@testing-library/react'
import { existsSync, readFileSync } from 'node:fs'
import { useEffect } from 'react'
import { useLocation } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { AppRoutes } from '../App'
import { ToastHost } from '../components/ToastHost'
import {
  BACKOFF_AFTER_DISMISSALS,
  BACKOFF_EVERY_GAMES,
  EVERY_GAMES,
  FIRST_AFTER_GAMES,
  FLYER,
  MIN_MINUTES_BETWEEN,
  SHOW_DELAY_MS,
  STORAGE_KEY,
} from '../config/guestPopup'
import { adoptSession, getAuthToken } from '../lib/account'
import { countFinishedGame, loadPopupState, popupDue, type GuestPopupState } from '../lib/guestPopup'
import { getProfile } from '../lib/profileStore'
import { clearMemoryStorage } from '../lib/storage'
import { accountProfile, accountStats, fakeFetch } from '../test/fakeFetch'
import { FakeWebSocket } from '../test/fakeWebSocket'
import { profileFx, roomFx } from '../test/fixtures'
import { renderWithRoom, saveTestProfile } from '../test/render'
import type { RoomPublic } from '../types/protocol'

const FINISHED: RoomPublic = { ...roomFx.roomFinished, endReason: 'completed' } as RoomPublic
const ME = FINISHED.hostId
const LOBBY: RoomPublic = { ...FINISHED, status: 'lobby' }
const PLAYING: RoomPublic = {
  ...FINISHED,
  status: 'playing',
  players: FINISHED.players.map((p) => ({ ...p, inGame: true })),
}
const MIN = 60_000

const CONFIGURED_FLYER = { ...FLYER }
let api: ReturnType<typeof fakeFetch>
let where = ''

beforeEach(() => {
  FakeWebSocket.reset()
  api = fakeFetch()
  FLYER.src = null // text version unless a test sets one
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'Date'] })
})
afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
  localStorage.clear()
  clearMemoryStorage()
  Object.assign(FLYER, CONFIGURED_FLYER)
})

function Where() {
  const location = useLocation()
  useEffect(() => {
    where = location.pathname + location.search
  }, [location])
  return null
}

const seed = (state: Partial<GuestPopupState>) =>
  localStorage.setItem(
    STORAGE_KEY,
    JSON.stringify({ gamesSinceShown: 0, totalGames: 0, lastShownAt: null, dismissalsInARow: 0, ...state }),
  )

async function settle() {
  await act(async () => {
    for (let i = 0; i < 4; i++) await Promise.resolve()
  })
}

/** Home → Create room → lobby of FINISHED's room as its host. */
async function inRoom() {
  const view = renderWithRoom(
    <>
      <Where />
      <AppRoutes />
      <ToastHost />
    </>,
    { route: '/' },
  )
  const ws = view.ws
  await settle()
  fireEvent.click(screen.getByRole('button', { name: 'Create room' }))
  await settle()
  const create = ws.frames().find((f) => f.type === 'room:create')!
  ws.ack({ playerId: ME, roomToken: 'tok-1', room: LOBBY }, create.id)
  await settle()
  return ws
}

/** One game: playing, then gameOver and the finished room (results screen). */
function playGame(ws: FakeWebSocket) {
  act(() => ws.receive({ type: 'room:state', data: PLAYING }))
  act(() => ws.receive({ type: 'game:event', data: roomFx.gameOverEvent }))
  act(() => ws.receive({ type: 'room:state', data: FINISHED }))
}

const wait = (ms: number) => act(() => vi.advanceTimersByTime(ms))
const popup = () => screen.queryByRole('dialog', { name: 'Make your profile permanent' })

// ----- counters ---------------------------------------------------------------------------

describe('popup counters', () => {
  it('first after FIRST_AFTER_GAMES games, then every EVERY_GAMES and at least MIN_MINUTES_BETWEEN apart', () => {
    const now = Date.now()
    expect(popupDue({ gamesSinceShown: 1, totalGames: FIRST_AFTER_GAMES - 1, lastShownAt: null, dismissalsInARow: 0 }, now)).toBe(false)
    expect(popupDue({ gamesSinceShown: 2, totalGames: FIRST_AFTER_GAMES, lastShownAt: null, dismissalsInARow: 0 }, now)).toBe(true)
    const shown = { totalGames: 10, dismissalsInARow: 1 }
    expect(popupDue({ ...shown, gamesSinceShown: EVERY_GAMES - 1, lastShownAt: now - 60 * MIN }, now)).toBe(false)
    expect(popupDue({ ...shown, gamesSinceShown: EVERY_GAMES, lastShownAt: now - 60 * MIN }, now)).toBe(true)
    expect(popupDue({ ...shown, gamesSinceShown: EVERY_GAMES, lastShownAt: now - (MIN_MINUTES_BETWEEN - 1) * MIN }, now)).toBe(false)
    expect(popupDue({ ...shown, gamesSinceShown: EVERY_GAMES, lastShownAt: now - MIN_MINUTES_BETWEEN * MIN }, now)).toBe(true)
  })

  it(`backs off to every ${BACKOFF_EVERY_GAMES} games after ${BACKOFF_AFTER_DISMISSALS} dismissals in a row`, () => {
    const now = Date.now()
    const base = { totalGames: 30, lastShownAt: now - 60 * MIN, dismissalsInARow: BACKOFF_AFTER_DISMISSALS }
    expect(popupDue({ ...base, gamesSinceShown: EVERY_GAMES }, now)).toBe(false)
    expect(popupDue({ ...base, gamesSinceShown: BACKOFF_EVERY_GAMES - 1 }, now)).toBe(false)
    expect(popupDue({ ...base, gamesSinceShown: BACKOFF_EVERY_GAMES }, now)).toBe(true)
  })

  it('persist in localStorage across reloads', () => {
    countFinishedGame()
    countFinishedGame()
    clearMemoryStorage() // a reload keeps only localStorage
    expect(JSON.parse(localStorage.getItem(STORAGE_KEY)!)).toMatchObject({ gamesSinceShown: 2, totalGames: 2 })
    expect(loadPopupState()).toMatchObject({ gamesSinceShown: 2, totalGames: 2, lastShownAt: null, dismissalsInARow: 0 })
  })

  it('survive broken or blocked localStorage and bad stored values', () => {
    localStorage.setItem(STORAGE_KEY, '{not json')
    expect(loadPopupState()).toEqual({ gamesSinceShown: 0, totalGames: 0, lastShownAt: null, dismissalsInARow: 0 })
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ gamesSinceShown: -4, totalGames: 'x', lastShownAt: 'y' }))
    expect(loadPopupState()).toEqual({ gamesSinceShown: 0, totalGames: 0, lastShownAt: null, dismissalsInARow: 0 })
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked')
    })
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('blocked')
    })
    expect(() => countFinishedGame()).not.toThrow()
    countFinishedGame()
    expect(loadPopupState().totalGames).toBe(2)
  })
})

// ----- when it appears --------------------------------------------------------------------

describe('guest signup popup: when', () => {
  it('shows only after the second finished game, about 1.5 s after the results', async () => {
    saveTestProfile()
    const ws = await inRoom()
    playGame(ws)
    wait(SHOW_DELAY_MS + 1000)
    expect(popup()).toBeNull()
    expect(loadPopupState()).toMatchObject({ totalGames: 1, gamesSinceShown: 1 })
    act(() => ws.receive({ type: 'room:state', data: LOBBY }))
    playGame(ws)
    expect(screen.getByRole('heading', { name: 'Game over' })).toBeInTheDocument()
    wait(SHOW_DELAY_MS - 100)
    expect(popup()).toBeNull()
    wait(100)
    expect(popup()).toBeInTheDocument()
    expect(loadPopupState().lastShownAt).toBe(Date.now())
  })

  it('never for registered players', async () => {
    adoptSession({ token: 'jwt-1', profile: profileFx.me.profile, stats: profileFx.me.stats })
    seed({ totalGames: 9, gamesSinceShown: 9 })
    const ws = await inRoom()
    playGame(ws)
    wait(SHOW_DELAY_MS * 3)
    expect(popup()).toBeNull()
    expect(loadPopupState().totalGames).toBe(9) // their games are not counted
  })

  it('never during play or on the waiting screen of a player who forfeited', async () => {
    saveTestProfile()
    seed({ totalGames: 9, gamesSinceShown: 9 })
    const ws = await inRoom()
    act(() => ws.receive({ type: 'room:state', data: PLAYING }))
    wait(SHOW_DELAY_MS * 3)
    expect(popup()).toBeNull()
    const forfeited = { ...PLAYING, players: PLAYING.players.map((p) => ({ ...p, inGame: p.id !== ME })) }
    act(() => ws.receive({ type: 'room:state', data: forfeited }))
    wait(SHOW_DELAY_MS * 3)
    expect(popup()).toBeNull()
  })

  it('waits for another dialog (Leave) to close first', async () => {
    saveTestProfile()
    seed({ totalGames: 9, gamesSinceShown: 9 })
    const ws = await inRoom()
    playGame(ws)
    fireEvent.click(screen.getByRole('button', { name: 'Leave' }))
    wait(SHOW_DELAY_MS * 3)
    expect(popup()).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Stay' }))
    wait(400)
    expect(popup()).toBeInTheDocument()
  })

  it('respects the 10-minute minimum between showings', async () => {
    saveTestProfile()
    seed({ totalGames: 9, gamesSinceShown: EVERY_GAMES - 1, lastShownAt: Date.now() - 5 * MIN })
    const ws = await inRoom()
    playGame(ws)
    wait(SHOW_DELAY_MS * 2)
    expect(popup()).toBeNull()
    expect(loadPopupState().gamesSinceShown).toBe(EVERY_GAMES)
    act(() => ws.receive({ type: 'room:state', data: LOBBY }))
    wait(6 * MIN)
    playGame(ws)
    wait(SHOW_DELAY_MS)
    expect(popup()).toBeInTheDocument()
  })

  it('the old post-game account prompt card is gone', async () => {
    saveTestProfile()
    const ws = await inRoom()
    playGame(ws)
    wait(SHOW_DELAY_MS)
    expect(screen.queryByText(/Not now|Don't ask again/)).not.toBeInTheDocument()
  })
})

// ----- what it does -----------------------------------------------------------------------

async function shown() {
  saveTestProfile()
  seed({ totalGames: 9, gamesSinceShown: 9, dismissalsInARow: 1 })
  const ws = await inRoom()
  playGame(ws)
  wait(SHOW_DELAY_MS)
  return { ws, dialog: popup()! }
}

describe('guest signup popup: content and buttons', () => {
  it('text version: title, the offer line, and both buttons; the backdrop does not close it', async () => {
    const { dialog } = await shown()
    expect(within(dialog).getByRole('heading', { name: 'Make your profile permanent' })).toBeVisible()
    expect(dialog).toHaveTextContent('Save your avatar, stats, and friends on any device.')
    expect(within(dialog).getByRole('button', { name: 'Create free account' })).toHaveClass('btn--primary', 'btn--block')
    expect(within(dialog).getByRole('button', { name: 'Maybe later' })).toBeInTheDocument()
    expect(within(dialog).getByRole('button', { name: 'Close' })).toBeInTheDocument()
    fireEvent.mouseDown(dialog.parentElement!)
    expect(popup()).toBeInTheDocument()
  })

  it.each(['Maybe later', 'Close'])('"%s" closes it and updates the counters', async (name) => {
    const { dialog } = await shown()
    fireEvent.click(within(dialog).getByRole('button', { name }))
    expect(popup()).toBeNull()
    expect(loadPopupState()).toMatchObject({ dismissalsInARow: 2, gamesSinceShown: 0, lastShownAt: Date.now() })
  })

  it('Escape closes it like Maybe later; Tab stays inside', async () => {
    const { dialog } = await shown()
    const buttons = within(dialog).getAllByRole('button')
    expect(buttons[0]).toHaveFocus()
    buttons.at(-1)!.focus()
    fireEvent.keyDown(document, { key: 'Tab' })
    expect(buttons[0]).toHaveFocus()
    fireEvent.keyDown(document, { key: 'Tab', shiftKey: true })
    expect(buttons.at(-1)).toHaveFocus()
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(popup()).toBeNull()
    expect(loadPopupState().dismissalsInARow).toBe(2)
  })

  it('"Create free account" goes to signup with the room as the return, and counts a conversion', async () => {
    const { dialog } = await shown()
    fireEvent.click(within(dialog).getByRole('button', { name: 'Create free account' }))
    await settle()
    expect(where).toBe(`/profile?next=${encodeURIComponent(`/room/${FINISHED.code}`)}`)
    expect(screen.getByRole('tab', { name: 'Create account', selected: true })).toBeInTheDocument()
    expect(loadPopupState()).toMatchObject({ dismissalsInARow: 0, gamesSinceShown: 0 })
  })

  it('with a flyer: the image on top, title kept for screen readers; a failed image falls back to text', async () => {
    FLYER.src = '/flyer.png'
    FLYER.alt = 'A test flyer'
    const { dialog } = await shown()
    const img = within(dialog).getByRole('img', { name: 'A test flyer' })
    expect(img).toHaveClass('guest-popup__flyer')
    expect(within(dialog).getByRole('heading', { name: 'Make your profile permanent' })).toHaveClass('visually-hidden')
    expect(dialog).toHaveTextContent('Save your avatar, stats, and friends on any device.')
    fireEvent.error(img)
    expect(within(dialog).queryByRole('img')).toBeNull()
    expect(within(dialog).getByRole('heading', { name: 'Make your profile permanent' })).not.toHaveClass('visually-hidden')
    expect(within(dialog).getByRole('button', { name: 'Create free account' })).toBeInTheDocument()
  })

  it('the configured flyer is the image in frontend/public, with alt text', () => {
    expect(existsSync(`public/${decodeURI(CONFIGURED_FLYER.src!)}`)).toBe(true)
    expect(CONFIGURED_FLYER.alt).toMatch(/keep the fun going/i)
  })

  it('the flyer is not loaded anywhere until the popup shows', async () => {
    FLYER.src = '/flyer.png'
    saveTestProfile()
    const ws = await inRoom()
    playGame(ws)
    expect(document.querySelector('img[src="/flyer.png"], link[href="/flyer.png"]')).toBeNull()
  })
})

// ----- signing up and coming back ---------------------------------------------------------

describe('after signing up from the popup', () => {
  async function signUp(ws: FakeWebSocket) {
    const dialog = popup()!
    fireEvent.click(within(dialog).getByRole('button', { name: 'Create free account' }))
    await settle()
    const card = screen.getByRole('region', { name: 'Save your profile' })
    fireEvent.change(within(card).getByLabelText('Username'), { target: { value: 'sam_1' } })
    fireEvent.change(within(card).getByLabelText('Password'), { target: { value: 'correct horse' } })
    api.reply(201, { token: 'jwt-1', profile: accountProfile })
    api.reply(200, { profile: accountProfile, stats: accountStats })
    fireEvent.click(within(card).getByRole('button', { name: 'Create account' }))
    await settle()
    return ws.frames().filter((f) => f.type === 'room:join').at(-1)
  }

  it('re-joins the same room with the seat token and the new login, then lands in it', async () => {
    const { ws } = await shown()
    const join = await signUp(ws)
    expect(getAuthToken()).toBe('jwt-1')
    expect(getProfile()?.type).toBe('registered')
    expect(join).toMatchObject({ payload: { code: FINISHED.code, roomToken: 'tok-1', authToken: 'jwt-1' } })
    const registered = { ...FINISHED, players: FINISHED.players.map((p) => (p.id === ME ? { ...p, type: 'registered' } : p)) }
    ws.ack({ playerId: ME, roomToken: 'tok-1', room: registered }, join!.id)
    await settle()
    expect(where).toBe(`/room/${FINISHED.code}`)
    expect(screen.getByRole('heading', { name: 'Game over' })).toBeInTheDocument()
    expect(popup()).toBeNull()
    expect(loadPopupState().dismissalsInARow).toBe(0)
  })

  it('goes home with a message if the room is gone', async () => {
    const { ws } = await shown()
    const join = await signUp(ws)
    ws.nack('ROOM_NOT_FOUND', 'Gone.', join!.id)
    await settle()
    expect(where).toBe('/')
    expect(screen.getByRole('alert')).toHaveTextContent(`We couldn't take you back to room ${FINISHED.code}.`)
  })
})

// ----- layout -----------------------------------------------------------------------------

describe('layout', () => {
  it('320px: the flyer fits (contain, at most 60% of the height), buttons stay on screen', () => {
    const css = readFileSync('src/styles/components.css', 'utf8')
    const rule = (name: string) => css.match(new RegExp(`\\.${name} \\{([^}]*)\\}`))![1]
    expect(rule('guest-popup__flyer')).toMatch(/object-fit: contain/)
    expect(rule('guest-popup__flyer')).toMatch(/max-height: 60dvh/)
    expect(rule('guest-popup__flyer')).toMatch(/width: 100%/)
    expect(rule('modal__actions')).toMatch(/flex-shrink: 0/)
    expect(rule('modal__body')).toMatch(/min-height: 0/)
    expect(rule('modal__box')).toMatch(/max-height: calc\(100dvh - 32px\)/)
  })
})
