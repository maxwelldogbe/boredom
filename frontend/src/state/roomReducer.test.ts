import { describe, expect, it } from 'vitest'
import { roomFx, rpsFx } from '../test/fixtures'
import { initialRoomState, MAX_EVENTS, roomReducer, type RoomState } from './roomReducer'

const seated = (): RoomState =>
  roomReducer(initialRoomState, { type: 'seated', playerId: 'p1', room: roomFx.roomLobby2 })

describe('roomReducer', () => {
  it('tracks connection status', () => {
    expect(roomReducer(initialRoomState, { type: 'connection', status: 'connected' }).connection).toBe('connected')
  })

  it('stores the seat and clears a previous seat-lost message', () => {
    const lost = roomReducer(initialRoomState, { type: 'seatLost', message: 'gone' })
    const s = roomReducer(lost, { type: 'seated', playerId: 'p1', room: roomFx.roomLobby2 })
    expect(s.playerId).toBe('p1')
    expect(s.room?.code).toBe(roomFx.roomLobby2.code)
    expect(s.seatLost).toBeNull()
  })

  it('stores the latest game view and the server clock offset', () => {
    const push = rpsFx.duelReveal.push
    const s = roomReducer(seated(), { type: 'gameView', push, receivedAt: push.serverNow - 250 })
    expect(s.game).toBe(push)
    expect(s.clockOffset).toBe(250)
  })

  it('records gameOver results and caps the event list', () => {
    let s = seated()
    for (let i = 0; i < MAX_EVENTS + 5; i++) {
      s = roomReducer(s, { type: 'gameEvent', event: { kind: 'reveal', data: { i } } })
    }
    expect(s.events).toHaveLength(MAX_EVENTS)
    s = roomReducer(s, { type: 'gameEvent', event: roomFx.gameOverEvent })
    expect(s.lastResults).toEqual((roomFx.gameOverEvent.data as { results: unknown }).results)
  })

  it('clears the old game when a new one starts or the room returns to the lobby', () => {
    let s = roomReducer(seated(), { type: 'gameView', push: rpsFx.duelDone.push, receivedAt: 0 })
    s = roomReducer(s, { type: 'gameEvent', event: roomFx.gameOverEvent })
    s = roomReducer(s, { type: 'roomState', room: roomFx.roomFinished })
    expect(s.game).not.toBeNull()
    expect(s.lastResults).not.toBeNull()
    const lobby = roomReducer(s, { type: 'roomState', room: { ...roomFx.roomFinished, status: 'lobby' } })
    expect(lobby.game).toBeNull()
    const playing = roomReducer(lobby, { type: 'roomState', room: { ...roomFx.roomFinished, status: 'playing' } })
    expect(playing.lastResults).toBeNull()
    expect(playing.events).toEqual([])
  })

  it('left and seatLost reset the room but keep connection and toasts', () => {
    let s = roomReducer(seated(), { type: 'connection', status: 'connected' })
    s = roomReducer(s, { type: 'toast', toast: { id: 1, message: 'hi', tone: 'info' } })
    const left = roomReducer(s, { type: 'left' })
    expect(left.room).toBeNull()
    expect(left.connection).toBe('connected')
    expect(left.toasts).toHaveLength(1)
    const lost = roomReducer(s, { type: 'seatLost', message: 'You joined from another tab.' })
    expect(lost.room).toBeNull()
    expect(lost.seatLost).toBe('You joined from another tab.')
  })

  it('keeps at most 3 toasts and dismisses by id', () => {
    let s = initialRoomState
    for (let id = 1; id <= 5; id++) s = roomReducer(s, { type: 'toast', toast: { id, message: `${id}`, tone: 'info' } })
    expect(s.toasts.map((t) => t.id)).toEqual([3, 4, 5])
    expect(roomReducer(s, { type: 'dismissToast', id: 4 }).toasts.map((t) => t.id)).toEqual([3, 5])
  })
})
