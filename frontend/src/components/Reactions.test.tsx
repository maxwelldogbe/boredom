import { act, fireEvent, screen, within } from '@testing-library/react'
import { readFileSync } from 'node:fs'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { TopBar } from '../pages/room/TopBar'
import { C } from '../lib/constants'
import { HIDE_REACTIONS_KEY, setReactionsHidden } from '../lib/reactionsPref'
import { clearMemoryStorage } from '../lib/storage'
import { FakeWebSocket } from '../test/fakeWebSocket'
import { roomFx } from '../test/fixtures'
import { renderWithRoom } from '../test/render'
import { ReactionLayer } from './Reactions'
import { ToastHost } from './ToastHost'

const room = roomFx.roomLobbyReadySome
const me = room.hostId
const ann = room.players.find((p) => p.nickname === 'Ann')!

beforeEach(() => FakeWebSocket.reset())
afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
  localStorage.clear()
  clearMemoryStorage()
  setReactionsHidden(false)
  localStorage.clear()
})

function mount() {
  return renderWithRoom(
    <>
      <TopBar room={room} me={me} onLeaving={() => {}} onLeft={() => {}} />
      <ReactionLayer room={room} />
      <ToastHost />
    </>,
  )
}

const toggle = () => screen.getByRole('button', { name: 'Send a reaction' })
const picker = () => screen.queryByRole('group', { name: 'Reactions' })
let n = 0
const push = (ws: FakeWebSocket, emoji = '🔥', player = ann) =>
  act(() => ws.receive({ type: 'room:reaction', data: { id: `r_${++n}`, playerId: player.id, nickname: player.nickname, emoji } }))

describe('reaction button and popover', () => {
  it('is a 44px button next to Menu, closed by default', () => {
    mount()
    expect(toggle()).toHaveAttribute('aria-expanded', 'false')
    expect(toggle()).toHaveClass('reactions-picker__toggle')
    expect(picker()).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Menu' })).toBeInTheDocument()
  })

  it('opens one row of the 8 allowed emojis; tapping one sends it and closes', async () => {
    const { ws } = mount()
    fireEvent.click(toggle())
    const buttons = within(picker()!).getAllByRole('button')
    expect(buttons.map((b) => b.textContent)).toEqual(C.REACTION_EMOJIS)
    expect(buttons.every((b) => b.getAttribute('aria-label')?.startsWith('React '))).toBe(true)
    fireEvent.click(within(picker()!).getByRole('button', { name: 'React fire' }))
    expect(ws.lastFrame()).toMatchObject({ type: 'room:react', payload: { emoji: '🔥' } })
    expect(picker()).not.toBeInTheDocument()
    await act(async () => ws.ack({}))
  })

  it('only ever sends emojis from REACTION_EMOJIS', () => {
    const { ws } = mount()
    for (const emoji of C.REACTION_EMOJIS) {
      fireEvent.click(toggle())
      fireEvent.click(within(picker()!).getByText(emoji))
    }
    const sent = ws.frames().filter((f) => f.type === 'room:react').map((f) => f.payload.emoji)
    expect(sent).toEqual(C.REACTION_EMOJIS)
  })

  it('closes on Escape and on a tap outside', () => {
    mount()
    fireEvent.click(toggle())
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(picker()).not.toBeInTheDocument()
    fireEvent.click(toggle())
    fireEvent.pointerDown(document.body)
    expect(picker()).not.toBeInTheDocument()
  })

  it('a cooldown rejection is quiet, a real failure is not', async () => {
    const { ws } = mount()
    fireEvent.click(toggle())
    fireEvent.click(screen.getByRole('button', { name: 'React party' }))
    await act(async () => ws.nack('RATE_LIMITED', 'Slow down a little.'))
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    fireEvent.click(toggle())
    fireEvent.click(screen.getByRole('button', { name: 'React party' }))
    await act(async () => ws.nack('NOT_IN_ROOM', 'You are not in a room.'))
    expect(screen.getByRole('alert')).toHaveTextContent('You are not in a room.')
  })
})

describe('incoming reactions', () => {
  it('show the emoji with the sender name and avatar, then disappear', () => {
    vi.useFakeTimers()
    const { ws } = mount()
    push(ws, '😂')
    const shown = screen.getByTestId('reaction')
    expect(shown).toHaveTextContent('😂')
    expect(shown).toHaveTextContent('Ann')
    expect(shown.querySelector('.chip__avatar')).not.toBeNull()
    expect(shown.style.animationDuration).toBe(`${C.REACTION_DISPLAY_MS}ms`)
    act(() => vi.advanceTimersByTime(C.REACTION_DISPLAY_MS))
    expect(screen.queryByTestId('reaction')).not.toBeInTheDocument()
  })

  it(`keeps at most ${C.REACTION_MAX_ON_SCREEN} on screen, dropping the oldest`, () => {
    const { ws } = mount()
    const emojis = ['👏', '😂', '😮', '🔥', '😭', '🤔', '🎉', '❤️']
    emojis.forEach((e) => push(ws, e))
    const shown = screen.getAllByTestId('reaction').map((r) => r.querySelector('.reaction__emoji')!.textContent)
    expect(shown).toEqual(emojis.slice(-C.REACTION_MAX_ON_SCREEN))
  })

  it('never blocks a tap and sits below dialogs and toasts', () => {
    const css = readFileSync('src/styles/room.css', 'utf8')
    const layer = css.match(/\.reactions \{([^}]*)\}/)![1]
    expect(layer).toMatch(/pointer-events: none/)
    expect(Number(layer.match(/z-index: (\d+)/)![1])).toBeLessThan(20)
    const { ws } = mount()
    push(ws)
    expect(document.querySelector('.reactions')).toHaveAttribute('aria-hidden', 'true')
  })

  it('reduced motion: a small static stack, no animation', () => {
    vi.stubGlobal('matchMedia', (query: string) => ({ matches: query.includes('reduce'), addEventListener() {}, removeEventListener() {} }))
    const { ws } = mount()
    push(ws, '🎉')
    expect(document.querySelector('.reactions')).toHaveClass('reactions--still')
    const shown = screen.getByTestId('reaction')
    expect(shown).toHaveTextContent('🎉')
    expect(shown).toHaveTextContent('Ann')
    expect(shown.style.animationDuration).toBe('')
    const css = readFileSync('src/styles/room.css', 'utf8')
    expect(css).toMatch(/\.reactions--still \.reaction \{[^}]*animation: none/)
  })
})

describe('Hide reactions', () => {
  it('the menu toggle hides the button and every incoming reaction, and is remembered', () => {
    const { ws, unmount } = mount()
    push(ws)
    expect(screen.getByTestId('reaction')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Menu' }))
    const hide = screen.getByRole('button', { name: 'Hide reactions' })
    expect(hide).toHaveAttribute('aria-pressed', 'false')
    fireEvent.click(hide)
    expect(localStorage.getItem(HIDE_REACTIONS_KEY)).toBe('1')
    expect(screen.getByRole('button', { name: '✓ Hide reactions' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.queryByRole('button', { name: 'Send a reaction' })).not.toBeInTheDocument()
    expect(document.querySelector('.reactions')).toBeNull()
    push(ws, '❤️')
    expect(screen.queryByTestId('reaction')).not.toBeInTheDocument()
    unmount()

    FakeWebSocket.reset()
    const again = mount()
    expect(screen.queryByRole('button', { name: 'Send a reaction' })).not.toBeInTheDocument()
    push(again.ws)
    expect(document.querySelector('.reactions')).toBeNull()
  })

  it('turning it off again brings the button back', () => {
    localStorage.setItem(HIDE_REACTIONS_KEY, '1')
    mount()
    expect(screen.queryByRole('button', { name: 'Send a reaction' })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Menu' }))
    fireEvent.click(screen.getByRole('button', { name: '✓ Hide reactions' }))
    expect(localStorage.getItem(HIDE_REACTIONS_KEY)).toBe('0')
    expect(screen.getByRole('button', { name: 'Send a reaction' })).toBeInTheDocument()
  })
})
