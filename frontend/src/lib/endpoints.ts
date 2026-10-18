/** Backend URLs. In dev both are same-origin and go through the Vite proxy. */

type LocationLike = Pick<Location, 'protocol' | 'host'>

/** WebSocket URL: VITE_WS_URL in production, else ws(s)://<this host>/ws/. */
export function wsUrl(
  env: ImportMetaEnv = import.meta.env,
  location: LocationLike = window.location,
): string {
  if (env.VITE_WS_URL) return env.VITE_WS_URL
  const scheme = location.protocol === 'https:' ? 'wss' : 'ws'
  return `${scheme}://${location.host}/ws/`
}

/** HTTP URL for an API path such as "/api/health". */
export function apiUrl(path: string, env: ImportMetaEnv = import.meta.env): string {
  return `${env.VITE_API_URL ?? ''}${path}`
}
