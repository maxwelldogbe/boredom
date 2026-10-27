import { act, fireEvent, screen, within } from '@testing-library/react'
import { readFileSync } from 'node:fs'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { ToastHost } from '../../components/ToastHost'
import { clearMemoryStorage } from '../../lib/storage'
import { FakeWebSocket } from '../../test/fakeWebSocket'
import { roomFx } from '../../test/fixtures'
import { renderWithRoom } from '../../test/render'
import type { RoomPublic } from '../../types/protocol'
import { Lobby } from './Lobby'
import { listNames, notReady, notReadyMessage } from './readyCheck'

beforeEach(() => FakeWebSocket.reset())
afterEach(() => {
  localStorage.clear()
  clearMemoryStorage()
})

const some = roomFx.roomLobbyReadySome // Ann ready, Bob and Dan not, Cat offline (ready)
const all = roomFx.roomLobbyReadyAll
const id = (room: RoomPublic, name: string) => room.players.find((p) => p.nickname === name)!.id
const host = some.hostId
const cards = () => within(screen.getByRole('list', { name: 'Players' })).getAllByRole('listitem')
const card = (name: string) => cards().find((li) => within(li).queryByText(name))!
const sent = (ws: FakeWebSocket, type: string) => ws.frames().filter((f) => f.type === type)

describe('ready check helpers', () => {
  it('lists up to three names, then "and N more"', () => {
    expect(listNames(['Ann'])).toBe('Ann')
    expect(listNames(['Ann', 'Bob'])).toBe('Ann and Bob')
    expect(listNames(['Ann', 'Bob', 'Cat'])).toBe('Ann, Bob and Cat')
    expect(listNames(['Ann', 'Bob', 'Cat', 'Dan', 'Eve'])).toBe('Ann, Bob, Cat and 2 more')
  })

  it('waits only for online non-host players who are not ready', () => {
    expect(notReady(some).map((p) => p.nickname)).toEqual(['Bob', 'Dan'])
    expect(notReady(all)).toEqual([])
    expect(notReadyMessage(notReady(some))).toBe("Bob and Dan aren't ready yet.")
  })
})

describe('Ready button (players)', () => {
  it('shows a large "I\'m ready" button for a player once a game is picked, and sends room:ready', async () => {
    const { ws } = renderWithRoom(<Lobby room={some} me={id(some, 'Bob')} />)
    const button = screen.getByRole('button', { name: "I'm ready" })
    expect(button).toHaveClass('btn--block', 'lobby__ready')
    expect(button).toHaveAttribute('aria-pressed', 'false')
    fireEvent.click(button)
    expect(ws.lastFrame()).toMatchObject({ type: 'room:ready', payload: { ready: true } })
    await act(async () => ws.ack({}))
  })

  it('reads "Ready ✓" when ready, and tapping again undoes it', async () => {
    const { ws } = renderWithRoom(<Lobby room={some} me={id(some, 'Ann')} />)
    const button = screen.getByRole('button', { name: 'Ready ✓' })
    expect(button).toHaveAttribute('aria-pressed', 'true')
    fireEvent.click(button)
    expect(ws.lastFrame()).toMatchObject({ type: 'room:ready', payload: { ready: false } })
    await act(async () => ws.ack({}))
  })

  it('sits above the room code so it is visible without scrolling', () => {
    renderWithRoom(<Lobby room={some} me={id(some, 'Bob')} />)
    const ready = screen.getByRole('button', { name: "I'm ready" })
    const code = screen.getByRole('button', { name: /Room code/ })
    expect(ready.compareDocumentPosition(code) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it('is not shown to the host', () => {
    renderWithRoom(<Lobby room={some} me={host} />)
    expect(screen.queryByRole('button', { name: "I'm ready" })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Ready ✓' })).not.toBeInTheDocument()
  })

  it('is hidden while no game is selected', () => {
    const noGame = { ...some, selectedGame: null, readyCheck: null }
    renderWithRoom(<Lobby room={noGame} me={id(some, 'Bob')} />)
    expect(screen.queryByRole('button', { name: "I'm ready" })).not.toBeInTheDocument()
    expect(screen.getByText("The host hasn't picked a game yet.")).toBeInTheDocument()
  })

  it('a failed request shows an error toast', async () => {
    const { ws } = renderWithRoom(
      <>
        <Lobby room={some} me={id(some, 'Bob')} />
        <ToastHost />
      </>,
    )
    fireEvent.click(screen.getByRole('button', { name: "I'm ready" }))
    await act(async () => ws.nack('INVALID_ACTION', 'You can only get ready in the lobby.'))
    expect(screen.getByRole('alert')).toHaveTextContent('You can only get ready in the lobby.')
  })
})

describe('Player list', () => {
  it('shows a Ready badge with a check mark, a Host badge, and offline', () => {
    renderWithRoom(<Lobby room={some} me={host} />)
    expect(within(card('Ann')).getByText('✓ Ready')).toBeInTheDocument()
    expect(within(card('Cat')).getByText('✓ Ready')).toBeInTheDocument()
    expect(within(card('Cat')).getByText('offline')).toBeInTheDocument()
    expect(within(card('Bob')).queryByText('✓ Ready')).not.toBeInTheDocument()
    expect(within(card('Host')).getByText('👑 Host')).toBeInTheDocument()
    expect(within(card('Host')).queryByText('✓ Ready')).not.toBeInTheDocument()
  })
})

describe('Start (host)', () => {
  it('shows "1 of 3 ready" next to a Start that is not disabled', () => {
    renderWithRoom(<Lobby room={some} me={host} />)
    expect(screen.getByRole('status')).toHaveTextContent('1 of 3 ready')
    const start = screen.getByRole('button', { name: 'Start game' })
    expect(start).toBeEnabled()
    expect(start).not.toHaveClass('lobby__start-btn--all-ready')
  })

  it('asks before starting early: names who is not ready, focuses Wait', async () => {
    const { ws } = renderWithRoom(<Lobby room={some} me={host} />)
    fireEvent.click(screen.getByRole('button', { name: 'Start game' }))
    const dialog = screen.getByRole('dialog', { name: 'Start without everyone?' })
    expect(within(dialog).getByText("Bob and Dan aren't ready yet.")).toBeInTheDocument()
    expect(within(dialog).getByRole('button', { name: 'Wait' })).toHaveFocus()
    expect(sent(ws, 'game:start')).toHaveLength(0)
    fireEvent.click(within(dialog).getByRole('button', { name: 'Wait' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(sent(ws, 'game:start')).toHaveLength(0)

    fireEvent.click(screen.getByRole('button', { name: 'Start game' }))
    fireEvent.click(screen.getByRole('button', { name: 'Start anyway' }))
    expect(ws.lastFrame().type).toBe('game:start')
    await act(async () => ws.ack({}))
  })

  it('lists three names and "and N more" for a big room', () => {
    const extra = ['Eve', 'Fay'].map((nickname, i) => ({ ...some.players[2], id: `p_extra${i}`, nickname }))
    const big = { ...some, players: [...some.players, ...extra], readyCheck: { count: 1, total: 5 } }
    renderWithRoom(<Lobby room={big} me={host} />)
    fireEvent.click(screen.getByRole('button', { name: 'Start game' }))
    expect(screen.getByText("Bob, Dan, Eve and 1 more aren't ready yet.")).toBeInTheDocument()
  })

  it('starts straight away, highlighted, when everyone is ready', async () => {
    const { ws } = renderWithRoom(<Lobby room={all} me={host} />)
    expect(screen.getByRole('status')).toHaveTextContent('✓ 3 of 3 ready')
    const start = screen.getByRole('button', { name: 'Start game' })
    expect(start).toHaveClass('lobby__start-btn--all-ready')
    fireEvent.click(start)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(ws.lastFrame().type).toBe('game:start')
    await act(async () => ws.ack({}))
  })

  it('is only disabled by the player minimum, never by the ready check', () => {
    const solo = { ...some, players: some.players.slice(0, 1), readyCheck: { count: 0, total: 0 } }
    renderWithRoom(<Lobby room={solo} me={host} />)
    expect(screen.getByRole('button', { name: 'Start game' })).toBeDisabled()
    expect(screen.getByText('Needs at least 2 players.')).toBeInTheDocument()
  })
})

describe('ready_reset', () => {
  it.each([
    ['game_changed', 'The host changed the game. Tap Ready again.'],
    ['settings_changed', 'The settings changed. Tap Ready again.'],
  ])('shows a toast for %s', (reason, message) => {
    const { ws } = renderWithRoom(
      <>
        <Lobby room={some} me={id(some, 'Ann')} />
        <ToastHost />
      </>,
    )
    act(() =>
      ws.receive({
        type: 'room:event',
        data: { kind: 'ready_reset', playerId: host, nickname: 'Host', data: { reason } },
      }),
    )
    expect(screen.getByText(message)).toBeInTheDocument()
  })
})

describe('older servers', () => {
  it('shows no ready UI and does not crash when room:state has no ready fields', () => {
    const old = { ...roomFx.roomLobby2, selectedGame: 'rps' as const }
    expect(old.readyCheck).toBeUndefined()
    const guest = old.players.find((p) => p.id !== old.hostId)!.id
    const { unmount } = renderWithRoom(<Lobby room={old} me={guest} />)
    expect(screen.queryByRole('button', { name: "I'm ready" })).not.toBeInTheDocument()
    expect(screen.queryByText('✓ Ready')).not.toBeInTheDocument()
    unmount()
    const { ws } = renderWithRoom(<Lobby room={old} me={old.hostId} />)
    expect(screen.queryByText(/of \d+ ready/)).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Start game' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(ws.lastFrame().type).toBe('game:start')
  })
})

describe('layout', () => {
  it('320px: the ready button and counter never force sideways scroll', () => {
    const css = readFileSync('src/styles/room.css', 'utf8')
    const rule = (name: string) => css.match(new RegExp(`\\.${name} \\{([^}]*)\\}`))?.[1] ?? ''
    expect(rule('lobby__ready')).toMatch(/min-height: 56px/)
    for (const name of ['lobby__ready', 'lobby__ready-count', 'lobby__start-btn--all-ready']) {
      expect(rule(name)).not.toMatch(/(^|\s)(width|min-width|white-space):/)
    }
    renderWithRoom(<Lobby room={some} me={id(some, 'Bob')} />)
    expect(screen.getByRole('button', { name: "I'm ready" })).toHaveClass('btn--block')
  })
})
