/**
 * GameSocket: the one WebSocket connection to /ws/.
 * Sends {id, type, payload}, resolves each request on its matching ack, forwards pushes,
 * reconnects with exponential backoff (capped), and rejects pending requests on disconnect.
 */
import type {
  AckData,
  ErrorCode,
  PushMessage,
  RequestPayload,
  RequestType,
  ServerMessage,
} from '../types/protocol'

export type SocketStatus = 'connecting' | 'connected' | 'disconnected'

/** A failed request: a protocol error code, or a transport problem. */
export class RequestError extends Error {
  readonly code: ErrorCode | 'DISCONNECTED' | 'TIMEOUT'
  constructor(code: RequestError['code'], message: string) {
    super(message)
    this.code = code
  }
}

export interface GameSocketOptions {
  url: string
  WebSocketImpl?: typeof WebSocket
  baseBackoffMs?: number
  maxBackoffMs?: number
  requestTimeoutMs?: number
}

interface Pending {
  resolve: (data: unknown) => void
  reject: (err: RequestError) => void
  timer: ReturnType<typeof setTimeout>
  frame: string
  sent: boolean
}

type Listener<T> = (value: T) => void

export class GameSocket {
  status: SocketStatus = 'disconnected'
  private ws: WebSocket | null = null
  private nextId = 1
  private pending = new Map<number, Pending>()
  private attempts = 0
  private everConnected = false
  private closedByUser = false
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null
  private pushListeners = new Set<Listener<PushMessage>>()
  private statusListeners = new Set<Listener<SocketStatus>>()
  private openListeners = new Set<Listener<boolean>>()
  private readonly opts: Required<GameSocketOptions>

  constructor(options: GameSocketOptions) {
    this.opts = {
      WebSocketImpl: WebSocket,
      baseBackoffMs: 500,
      maxBackoffMs: 10_000,
      requestTimeoutMs: 20_000,
      ...options,
    }
  }

  /** Open the connection (no-op if already open or opening). */
  connect(): void {
    this.closedByUser = false
    if (this.ws) return
    this.setStatus('connecting')
    const ws = new this.opts.WebSocketImpl(this.opts.url)
    this.ws = ws
    ws.onopen = () => {
      const isReconnect = this.everConnected
      this.everConnected = true
      this.attempts = 0
      this.setStatus('connected')
      for (const [, p] of this.pending) {
        if (!p.sent) {
          ws.send(p.frame)
          p.sent = true
        }
      }
      this.openListeners.forEach((fn) => fn(isReconnect))
    }
    ws.onmessage = (event: MessageEvent) => this.handleFrame(event.data)
    ws.onclose = () => this.handleClose(ws)
  }

  /** Close for good (no reconnect). */
  close(): void {
    this.closedByUser = true
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer)
    this.reconnectTimer = null
    const ws = this.ws
    if (ws) {
      this.handleClose(ws)
      ws.close()
    }
  }

  /** Send a request; resolves with the ack data or rejects with a RequestError. */
  request<K extends RequestType>(type: K, payload: RequestPayload<K>): Promise<AckData<K>> {
    const id = this.nextId++
    const frame = JSON.stringify({ id, type, payload })
    return new Promise<AckData<K>>((resolve, reject) => {
      if (this.status === 'disconnected' && this.closedByUser) {
        reject(new RequestError('DISCONNECTED', 'Not connected to the server.'))
        return
      }
      const timer = setTimeout(() => {
        this.pending.delete(id)
        reject(new RequestError('TIMEOUT', 'The server took too long to answer.'))
      }, this.opts.requestTimeoutMs)
      const entry: Pending = {
        resolve: (data) => resolve(data as AckData<K>),
        reject,
        timer,
        frame,
        sent: false,
      }
      this.pending.set(id, entry)
      if (this.status === 'connected' && this.ws) {
        this.ws.send(frame)
        entry.sent = true
      } else {
        this.connect()
      }
    })
  }

  onPush(fn: Listener<PushMessage>): () => void {
    this.pushListeners.add(fn)
    return () => this.pushListeners.delete(fn)
  }

  onStatus(fn: Listener<SocketStatus>): () => void {
    this.statusListeners.add(fn)
    return () => this.statusListeners.delete(fn)
  }

  /** Called on every successful open; the argument is true for re-connections. */
  onOpen(fn: Listener<boolean>): () => void {
    this.openListeners.add(fn)
    return () => this.openListeners.delete(fn)
  }

  private handleFrame(raw: unknown): void {
    if (typeof raw !== 'string') return
    let msg: ServerMessage
    try {
      msg = JSON.parse(raw) as ServerMessage
    } catch {
      return
    }
    if (!msg || typeof msg !== 'object' || typeof msg.type !== 'string') return
    if (msg.type === 'ack') {
      const entry = this.pending.get(msg.id)
      if (!entry) return
      this.pending.delete(msg.id)
      clearTimeout(entry.timer)
      if (msg.ok) entry.resolve(msg.data)
      else entry.reject(new RequestError(msg.error.code, msg.error.message))
      return
    }
    this.pushListeners.forEach((fn) => fn(msg as PushMessage))
  }

  private handleClose(ws: WebSocket): void {
    if (this.ws !== ws) return
    ws.onopen = ws.onmessage = ws.onclose = null
    this.ws = null
    for (const [id, p] of this.pending) {
      clearTimeout(p.timer)
      p.reject(new RequestError('DISCONNECTED', 'Lost connection to the server.'))
      this.pending.delete(id)
    }
    this.setStatus('disconnected')
    if (!this.closedByUser) this.scheduleReconnect()
  }

  private scheduleReconnect(): void {
    const delay = Math.min(this.opts.maxBackoffMs, this.opts.baseBackoffMs * 2 ** this.attempts)
    this.attempts += 1
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null
      this.connect()
    }, delay)
  }

  private setStatus(status: SocketStatus): void {
    if (this.status === status) return
    this.status = status
    this.statusListeners.forEach((fn) => fn(status))
  }
}
