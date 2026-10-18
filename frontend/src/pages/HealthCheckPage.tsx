import { useEffect, useState } from 'react'
import { apiUrl, wsUrl } from '../lib/endpoints'
import './HealthCheckPage.css'

type ApiState = 'loading' | 'ok' | 'error'
type SocketState = 'connecting' | 'connected' | 'disconnected'

/** F0 placeholder for "/": shows whether the backend API and WebSocket are reachable. */
export default function HealthCheckPage() {
  const [api, setApi] = useState<ApiState>('loading')
  const [socket, setSocket] = useState<SocketState>('connecting')
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    fetch(apiUrl('/api/health'), { signal: controller.signal })
      .then(async (res) => {
        const body: unknown = await res.json()
        const ok =
          res.ok && typeof body === 'object' && body !== null && 'ok' in body && body.ok === true
        setApi(ok ? 'ok' : 'error')
      })
      .catch(() => {
        if (!controller.signal.aborted) setApi('error')
      })
    const ws = new WebSocket(wsUrl())
    ws.onopen = () => setSocket('connected')
    ws.onclose = () => setSocket('disconnected')
    return () => {
      controller.abort()
      ws.onopen = ws.onclose = null
      ws.close()
    }
  }, [attempt])

  const retry = () => {
    setApi('loading')
    setSocket('connecting')
    setAttempt((n) => n + 1)
  }

  return (
    <main className="health">
      <h1>Boredom</h1>
      <p className="health__intro">Connection check</p>
      <dl className="health__list">
        <div>
          <dt>Server</dt>
          <dd data-state={api}>
            {api === 'loading' && 'Checking…'}
            {api === 'ok' && '✓ Online'}
            {api === 'error' && '✕ Not reachable'}
          </dd>
        </div>
        <div>
          <dt>Live connection</dt>
          <dd data-state={socket}>
            {socket === 'connecting' && 'Connecting…'}
            {socket === 'connected' && '✓ Connected'}
            {socket === 'disconnected' && '✕ Disconnected'}
          </dd>
        </div>
      </dl>
      {(api === 'error' || socket === 'disconnected') && (
        <>
          <p>The server may be waking up. This can take up to a minute.</p>
          <button type="button" className="health__retry" onClick={retry}>
            Retry
          </button>
        </>
      )}
    </main>
  )
}
