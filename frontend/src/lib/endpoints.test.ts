import { describe, expect, it } from 'vitest'
import { apiUrl, wsUrl } from './endpoints'

const env = (over: Partial<ImportMetaEnv> = {}) => ({ ...import.meta.env, VITE_WS_URL: undefined, VITE_API_URL: undefined, ...over })

describe('wsUrl', () => {
  it('uses same-origin /ws/ in dev (proxied)', () => {
    expect(wsUrl(env(), { protocol: 'http:', host: '192.168.1.5:5173' })).toBe('ws://192.168.1.5:5173/ws/')
  })
  it('uses wss on https pages', () => {
    expect(wsUrl(env(), { protocol: 'https:', host: 'boredom.app' })).toBe('wss://boredom.app/ws/')
  })
  it('prefers VITE_WS_URL', () => {
    expect(wsUrl(env({ VITE_WS_URL: 'wss://api.x/ws/' }), { protocol: 'https:', host: 'a' })).toBe('wss://api.x/ws/')
  })
})

describe('apiUrl', () => {
  it('is relative in dev', () => {
    expect(apiUrl('/api/health', env())).toBe('/api/health')
  })
  it('prefixes VITE_API_URL', () => {
    expect(apiUrl('/api/health', env({ VITE_API_URL: 'https://api.x' }))).toBe('https://api.x/api/health')
  })
})
