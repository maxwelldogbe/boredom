/** Shared pieces of the opt-in live tests (see live.test.tsx). */
import { GameSocket } from '../lib/socket'
import type { PushMessage } from '../types/protocol'
import type { GameViewPush } from '../types/views'

export const env = (globalThis as { process?: { env: Record<string, string | undefined> } }).process?.env ?? {}
const WS_URL = env.LIVE_WS_URL ?? 'ws://127.0.0.1:8000/ws/'

/** Node's WebSocket sends no Origin header (browsers always do); the backend requires one. */
class OriginWebSocket extends WebSocket {
  constructor(url: string | URL) {
    super(url, { headers: { Origin: 'http://localhost:5173' } } as unknown as string[])
  }
}
export const live = () => new GameSocket({ url: WS_URL, WebSocketImpl: OriginWebSocket })
export const T = { timeout: 15_000 }

/** A bare-socket player that records every game:view it receives. */
export function socketPlayer(sockets: GameSocket[]) {
  const socket = live()
  sockets.push(socket)
  const views: GameViewPush[] = []
  socket.onPush((m: PushMessage) => {
    if (m.type === 'game:view') views.push(m.data)
  })
  const latest = <V>() => views.at(-1)?.view as V
  return { socket, views, latest }
}

export const pause = (ms: number) => new Promise((r) => setTimeout(r, ms))
