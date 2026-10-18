import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import HealthCheckPage from './HealthCheckPage'

class FakeWebSocket {
  static instances: FakeWebSocket[] = []
  onopen: (() => void) | null = null
  onclose: (() => void) | null = null
  url: string
  constructor(url: string) {
    this.url = url
    FakeWebSocket.instances.push(this)
  }
  close() {}
}

function mockFetch(response: () => Promise<Response>) {
  vi.stubGlobal('fetch', vi.fn(response))
}

beforeEach(() => {
  FakeWebSocket.instances = []
  vi.stubGlobal('WebSocket', FakeWebSocket)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('HealthCheckPage', () => {
  it('shows loading, then online and connected', async () => {
    mockFetch(async () => new Response(JSON.stringify({ ok: true }), { status: 200 }))
    render(<HealthCheckPage />)
    expect(screen.getByText('Checking…')).toBeInTheDocument()
    expect(screen.getByText('Connecting…')).toBeInTheDocument()
    expect(await screen.findByText('✓ Online')).toBeInTheDocument()
    act(() => FakeWebSocket.instances.at(-1)?.onopen?.())
    expect(screen.getByText('✓ Connected')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Retry' })).not.toBeInTheDocument()
    expect(FakeWebSocket.instances.at(-1)?.url).toMatch(/\/ws\/$/)
  })

  it('shows an error with Retry when the server is unreachable', async () => {
    mockFetch(async () => {
      throw new TypeError('network')
    })
    render(<HealthCheckPage />)
    expect(await screen.findByText('✕ Not reachable')).toBeInTheDocument()
    act(() => FakeWebSocket.instances.at(-1)?.onclose?.())
    expect(screen.getByText('✕ Disconnected')).toBeInTheDocument()
    const before = FakeWebSocket.instances.length
    mockFetch(async () => new Response(JSON.stringify({ ok: true }), { status: 200 }))
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }))
    expect(await screen.findByText('✓ Online')).toBeInTheDocument()
    expect(FakeWebSocket.instances.length).toBeGreaterThan(before)
  })

  it('treats a non-ok health body as an error', async () => {
    mockFetch(async () => new Response(JSON.stringify({ ok: false }), { status: 200 }))
    render(<HealthCheckPage />)
    expect(await screen.findByText('✕ Not reachable')).toBeInTheDocument()
  })
})
