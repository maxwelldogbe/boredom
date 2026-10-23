/** A queue of canned JSON responses for the account API; records every request. */
import { vi } from 'vitest'

export interface FetchCall {
  url: string
  method: string
  headers: Record<string, string>
  body: unknown
}

export function fakeFetch() {
  const calls: FetchCall[] = []
  const replies: Array<{ status: number; body: unknown } | 'network'> = []
  const fn = vi.fn(async (url: string, init: RequestInit = {}) => {
    calls.push({
      url,
      method: init.method ?? 'GET',
      headers: (init.headers ?? {}) as Record<string, string>,
      body: init.body ? JSON.parse(init.body as string) : undefined,
    })
    const reply = replies.shift()
    if (!reply) throw new Error(`No canned reply for ${url}`)
    if (reply === 'network') throw new TypeError('Failed to fetch')
    return { ok: reply.status < 400, status: reply.status, json: async () => reply.body } as Response
  })
  vi.stubGlobal('fetch', fn)
  return {
    calls,
    reply(status: number, body: unknown) {
      replies.push({ status, body })
    },
    networkError() {
      replies.push('network')
    },
  }
}

export const accountProfile = {
  username: 'sam_1',
  nickname: 'Sam',
  color: '#E74C3C',
  avatar: { style: 'cutouts', seed: 'saved1' },
  type: 'registered' as const,
  createdAt: 1792324569015,
}

export const accountStats = { gamesPlayed: 3, wins: 1, byGame: { rps: { played: 3, wins: 1 } } }
