import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { asWebSocket, FakeWebSocket } from '../test/fakeWebSocket'
import { GameSocket, RequestError } from './socket'

function make() {
  return new GameSocket({ url: 'ws://test/ws/', WebSocketImpl: asWebSocket })
}

beforeEach(() => {
  FakeWebSocket.reset()
  vi.useFakeTimers()
})
afterEach(() => {
  vi.useRealTimers()
})

describe('GameSocket', () => {
  it('sends {id,type,payload} and resolves on the matching ack', async () => {
    const s = make()
    s.connect()
    FakeWebSocket.last().open()
    const p1 = s.request('room:peek', { code: 'ABCD' })
    const p2 = s.request('room:peek', { code: 'EFGH' })
    const [f1, f2] = FakeWebSocket.last().frames()
    expect(f1).toEqual({ id: 1, type: 'room:peek', payload: { code: 'ABCD' } })
    FakeWebSocket.last().ack({ exists: false }, f2.id)
    FakeWebSocket.last().ack({ exists: true }, f1.id)
    await expect(p1).resolves.toEqual({ exists: true })
    await expect(p2).resolves.toEqual({ exists: false })
  })

  it('rejects with the protocol error code on ok:false', async () => {
    const s = make()
    s.connect()
    FakeWebSocket.last().open()
    const p = s.request('game:start', {})
    FakeWebSocket.last().nack('NOT_HOST', 'Only the host can do that.')
    await expect(p).rejects.toMatchObject({ code: 'NOT_HOST', message: 'Only the host can do that.' })
    await expect(p).rejects.toBeInstanceOf(RequestError)
  })

  it('queues requests made while connecting and sends them on open', async () => {
    const s = make()
    const p = s.request('room:peek', { code: 'ABCD' })
    expect(s.status).toBe('connecting')
    expect(FakeWebSocket.last().sent).toHaveLength(0)
    FakeWebSocket.last().open()
    expect(FakeWebSocket.last().frames()[0].type).toBe('room:peek')
    FakeWebSocket.last().ack({ exists: false })
    await expect(p).resolves.toEqual({ exists: false })
  })

  it('forwards pushes and ignores junk frames', () => {
    const s = make()
    const pushes: unknown[] = []
    s.onPush((m) => pushes.push(m))
    s.connect()
    const ws = FakeWebSocket.last()
    ws.open()
    ws.onmessage?.({ data: 'not json' })
    ws.onmessage?.({ data: 42 })
    ws.receive({ type: 'ack', id: 999, ok: true, data: {} })
    ws.receive({ type: 'error', data: { code: 'BAD_MESSAGE', message: 'x' } })
    expect(pushes).toEqual([{ type: 'error', data: { code: 'BAD_MESSAGE', message: 'x' } }])
  })

  it('rejects pending requests on disconnect and reports status', async () => {
    const s = make()
    const statuses: string[] = []
    s.onStatus((st) => statuses.push(st))
    s.connect()
    FakeWebSocket.last().open()
    const p = s.request('room:leave', {})
    FakeWebSocket.last().drop()
    await expect(p).rejects.toMatchObject({ code: 'DISCONNECTED' })
    expect(statuses).toEqual(['connecting', 'connected', 'disconnected'])
  })

  it('reconnects with exponential backoff capped at 10 s and flags re-opens', () => {
    const s = make()
    const opens: boolean[] = []
    s.onOpen((again) => opens.push(again))
    s.connect()
    FakeWebSocket.last().open()
    const delays: number[] = []
    for (let i = 0; i < 7; i++) {
      const before = FakeWebSocket.instances.length
      FakeWebSocket.last().drop()
      let waited = 0
      while (FakeWebSocket.instances.length === before) {
        vi.advanceTimersByTime(100)
        waited += 100
      }
      delays.push(waited)
    }
    expect(delays).toEqual([500, 1000, 2000, 4000, 8000, 10000, 10000])
    FakeWebSocket.last().open()
    expect(opens).toEqual([false, true])
    FakeWebSocket.last().drop()
    vi.advanceTimersByTime(500)
    expect(FakeWebSocket.instances.length).toBe(9) // backoff reset after a good open
  })

  it('times out requests that never get an ack', async () => {
    const s = make()
    s.connect()
    FakeWebSocket.last().open()
    const p = s.request('room:peek', { code: 'ABCD' })
    vi.advanceTimersByTime(20_000)
    await expect(p).rejects.toMatchObject({ code: 'TIMEOUT' })
  })

  it('close() stops reconnecting', () => {
    const s = make()
    s.connect()
    FakeWebSocket.last().open()
    s.close()
    vi.advanceTimersByTime(60_000)
    expect(FakeWebSocket.instances).toHaveLength(1)
    expect(s.status).toBe('disconnected')
  })
})
