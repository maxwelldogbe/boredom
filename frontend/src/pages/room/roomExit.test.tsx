import { act, fireEvent, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { AppRoutes } from '../../App'
import { ToastHost } from '../../components/ToastHost'
import { adoptSession } from '../../lib/account'
import { resetRoomExits } from '../../lib/roomExit'
import { clearMemoryStorage } from '../../lib/storage'
import { fakeFetch } from '../../test/fakeFetch'
import { FakeWebSocket } from '../../test/fakeWebSocket'
import { profileFx, roomFx, soloFx } from '../../test/fixtures'
import { renderWithRoom, saveTestProfile } from '../../test/render'
import type { RoomPublic } from '../../types/protocol'

beforeEach(() => {
  FakeWebSocket.reset()
  fakeFetch()
})
afterEach(() => {
  vi.unstubAllGlobals()
  localStorage.clear()
  clearMemoryStorage()
  resetRoomExits()
})

const app = (route: string) =>
  renderWithRoom(
    <>
      <AppRoutes />
      <ToastHost />
    </>,
    { route },
  )

/** /room/:code rejoined by token as `me`. */
async function inRoom(room: RoomPublic, me: string) {
  localStorage.setItem('partypack.roomTokens', JSON.stringify({ [room.code]: 'tok' }))
  const r = app(`/room/${room.code}`)
  const join = r.ws.frames().find((f) => f.type === 'room:join')!
  await act(async () => r.ws.ack({ playerId: me, roomToken: 'tok', room }, join.id))
  return r
}

const peeked = (ws: FakeWebSocket) => ws.frames().some((f) => f.type === 'room:peek')

describe('leaving a room never shows the invite landing', () => {
  it('solo quit lands on /solo', async () => {
    adoptSession({ token: 'jwt-1', profile: profileFx.me.profile, stats: profileFx.me.stats })
    const { room, push } = soloFx.c4Playing
    const { ws } = await inRoom(room, room.players.find((p) => !p.bot)!.id)
    act(() => ws.receive({ type: 'game:view', data: push }))
    fireEvent.click(screen.getByRole('button', { name: 'Quit' }))
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Quit' }))
    await act(async () => ws.ack({}, ws.lastFrame().id))
    expect(screen.getByRole('heading', { name: 'Play alone' })).toBeInTheDocument()
    expect(screen.queryByText(/not found/)).not.toBeInTheDocument()
    expect(peeked(ws)).toBe(false)
  })

  it('a normal leave lands on Home', async () => {
    saveTestProfile()
    const room = roomFx.roomLobby2
    const { ws } = await inRoom(room, room.players[0].id)
    fireEvent.click(screen.getByRole('button', { name: 'Leave' }))
    fireEvent.click(screen.getByRole('button', { name: 'Leave room' }))
    expect(ws.lastFrame().type).toBe('room:leave')
    await act(async () => ws.ack({}, ws.lastFrame().id))
    expect(screen.getByRole('button', { name: 'Create room' })).toBeInTheDocument()
    expect(peeked(ws)).toBe(false)
  })
})

describe('a room that is gone', () => {
  it('an unexpected loss shows "This room closed"', async () => {
    saveTestProfile()
    localStorage.setItem('partypack.roomTokens', JSON.stringify({ ABCD: 'tok' }))
    const { ws } = app('/room/ABCD')
    await act(async () => ws.nack('ROOM_NOT_FOUND'))
    expect(screen.getByRole('heading', { name: 'This room closed' })).toBeInTheDocument()
    expect(screen.getByText('The room ended or the server restarted.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Go home' })).toBeInTheDocument()
    expect(peeked(ws)).toBe(false)
  })

  it('a pasted /join link for a missing room keeps the not-found landing', async () => {
    saveTestProfile()
    const { ws } = app('/join/WXYZ')
    const peek = ws.frames().find((f) => f.type === 'room:peek')!
    await act(async () => ws.ack(roomFx.peekMissing, peek.id))
    expect(screen.getByText('Room WXYZ not found')).toBeInTheDocument()
  })
})
