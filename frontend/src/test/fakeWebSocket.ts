/** Controllable stand-in for the browser WebSocket, for tests. */
export class FakeWebSocket {
  static instances: FakeWebSocket[] = []
  static reset() {
    FakeWebSocket.instances = []
  }
  static last(): FakeWebSocket {
    const ws = FakeWebSocket.instances.at(-1)
    if (!ws) throw new Error('no FakeWebSocket created')
    return ws
  }

  url: string
  sent: string[] = []
  closed = false
  onopen: ((ev?: unknown) => void) | null = null
  onmessage: ((ev: { data: unknown }) => void) | null = null
  onclose: ((ev?: unknown) => void) | null = null

  constructor(url: string) {
    this.url = url
    FakeWebSocket.instances.push(this)
  }
  send(data: string) {
    this.sent.push(data)
  }
  close() {
    this.closed = true
  }

  // ----- test controls -----
  open() {
    this.onopen?.()
  }
  receive(msg: unknown) {
    this.onmessage?.({ data: JSON.stringify(msg) })
  }
  drop() {
    this.onclose?.()
  }
  /** Parsed frames sent by the client. */
  frames(): { id: number; type: string; payload: Record<string, unknown> }[] {
    return this.sent.map((s) => JSON.parse(s))
  }
  lastFrame() {
    const f = this.frames().at(-1)
    if (!f) throw new Error('nothing sent')
    return f
  }
  ack(data: unknown, id = this.lastFrame().id) {
    this.receive({ type: 'ack', id, ok: true, data })
  }
  nack(code: string, message = code, id = this.lastFrame().id) {
    this.receive({ type: 'ack', id, ok: false, error: { code, message } })
  }
}

export const asWebSocket = FakeWebSocket as unknown as typeof WebSocket
