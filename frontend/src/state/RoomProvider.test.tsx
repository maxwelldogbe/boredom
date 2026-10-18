import { act, render } from '@testing-library/react'
import { useEffect } from 'react'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { createProfile, saveProfile } from '../lib/profileStore'
import { getRoomToken } from '../lib/roomTokens'
import { GameSocket } from '../lib/socket'
import { clearMemoryStorage } from '../lib/storage'
import { asWebSocket, FakeWebSocket } from '../test/fakeWebSocket'
import { roomFx } from '../test/fixtures'
import { useRoomActions, useRoomState, type RoomActions } from './context'
import type { RoomState } from './roomReducer'
import { RoomProvider } from './RoomProvider'

const probe: { actions?: RoomActions; state?: RoomState } = {}

function Probe() {
  const a = useRoomActions()
  const s = useRoomState()
  useEffect(() => {
    probe.actions = a
    probe.state = s
  })
  return null
}

const actions = (): RoomActions => probe.actions as RoomActions
const current = (): RoomState => probe.state as RoomState

function mount() {
  const socket = new GameSocket({ url: 'ws://t/ws/', WebSocketImpl: asWebSocket, baseBackoffMs: 1 })
  render(
    <RoomProvider socket={socket}>
      <Probe />
    </RoomProvider>,
  )
  const ws = FakeWebSocket.last()
  act(() => ws.open())
  return ws
}

const seat = roomFx.seatAck
const code = seat.room.code

beforeEach(() => {
  FakeWebSocket.reset()
  saveProfile(createProfile({ nickname: 'Sam', emoji: '😀', color: '#E74C3C' }))
})
afterEach(() => {
  localStorage.clear()
  clearMemoryStorage()
})

async function createSeat(ws: FakeWebSocket) {
  let created: Promise<string> = Promise.resolve('')
  act(() => {
    created = actions().createRoom()
  })
  expect(ws.lastFrame().type).toBe('room:create')
  expect(ws.lastFrame().payload.profile).toMatchObject({ nickname: 'Sam', type: 'guest' })
  expect(ws.lastFrame().payload.profile).not.toHaveProperty('stats')
  await act(async () => {
    ws.ack(seat)
    await created
  })
}

describe('RoomProvider', () => {
  it('creates a room, stores the roomToken and the seat', async () => {
    const ws = mount()
    await createSeat(ws)
    expect(getRoomToken(code)).toBe(seat.roomToken)
    expect(current().playerId).toBe(seat.playerId)
    expect(current().room?.code).toBe(code)
  })

  it('applies room:state pushes and game views', async () => {
    const ws = mount()
    await createSeat(ws)
    act(() => ws.receive({ type: 'room:state', data: roomFx.roomLobby2 }))
    expect(current().room?.players).toHaveLength(2)
  })

  it('re-joins with the stored token after the connection drops', async () => {
    const ws = mount()
    await createSeat(ws)
    act(() => ws.drop())
    expect(current().connection).toBe('disconnected')
    await act(async () => {
      await new Promise((r) => setTimeout(r, 10))
    })
    const ws2 = FakeWebSocket.last()
    expect(ws2).not.toBe(ws)
    act(() => ws2.open())
    expect(ws2.lastFrame()).toMatchObject({
      type: 'room:join',
      payload: { code, roomToken: seat.roomToken },
    })
    await act(async () => ws2.ack(seat))
    expect(current().room?.code).toBe(code)
  })

  it('a lost seat is final: no automatic rejoin', async () => {
    const ws = mount()
    await createSeat(ws)
    act(() => ws.receive({ type: 'error', data: { code: 'NOT_IN_ROOM', message: 'You joined from another tab.' } }))
    expect(current().room).toBeNull()
    expect(current().seatLost).toBe('You joined from another tab.')
    act(() => ws.drop())
    await act(async () => {
      await new Promise((r) => setTimeout(r, 10))
    })
    act(() => FakeWebSocket.last().open())
    expect(FakeWebSocket.last().sent).toHaveLength(0)
  })

  it('leaving deletes the stored token', async () => {
    const ws = mount()
    await createSeat(ws)
    let left: Promise<void> = Promise.resolve()
    act(() => {
      left = actions().leaveRoom()
    })
    await act(async () => {
      ws.ack({})
      await left
    })
    expect(getRoomToken(code)).toBeNull()
    expect(current().room).toBeNull()
  })

  it('joinRoom sends the stored token when there is one', async () => {
    const ws = mount()
    localStorage.setItem('partypack.roomTokens', JSON.stringify({ [code]: 'tok' }))
    act(() => {
      void actions().joinRoom(code.toLowerCase()).catch(() => {})
    })
    expect(ws.lastFrame()).toMatchObject({ type: 'room:join', payload: { code, roomToken: 'tok' } })
  })
})
