/** A queue of canned JSON responses for the account API; records every request. */
import { vi } from 'vitest'

export interface FetchCall {
  url: string
  method: string
  headers: Record<string, string>
  body: unknown
}

type Reply = { status: number; body: unknown } | 'network'

/** /api/me/* and /api/friends answer by URL (default: empty), so background requests don't take
 *  replies queued for other calls. They are recorded in `meCalls`, not `calls`. */
const ME_DEFAULTS: Record<string, Reply> = {
  '/api/me/stats': {
    status: 200,
    body: { totals: { played: 0, wins: 0, losses: 0, winRate: null }, favoriteGame: null, perGame: [], minGamesForRate: 5 },
  },
  '/api/me/recent-players': { status: 200, body: { players: [] } },
  '/api/friends': { status: 200, body: { friends: [], incoming: [], outgoing: [], blocked: [] } },
  '/api/me/settings': { status: 200, body: { presence: 'online' } },
}

export function fakeFetch() {
  const calls: FetchCall[] = []
  const meCalls: FetchCall[] = []
  const replies: Reply[] = []
  const routes: Record<string, Reply[]> = {}
  const answer = (reply: Reply | undefined, url: string) => {
    if (!reply) throw new Error(`No canned reply for ${url}`)
    if (reply === 'network') throw new TypeError('Failed to fetch')
    return { ok: reply.status < 400, status: reply.status, json: async () => reply.body } as Response
  }
  const fn = vi.fn(async (url: string, init: RequestInit = {}) => {
    const call = {
      url,
      method: init.method ?? 'GET',
      headers: (init.headers ?? {}) as Record<string, string>,
      body: init.body ? JSON.parse(init.body as string) : undefined,
    }
    if (url in ME_DEFAULTS) {
      meCalls.push(call)
      return answer(routes[url]?.shift() ?? ME_DEFAULTS[url], url)
    }
    calls.push(call)
    return answer(replies.shift(), url)
  })
  vi.stubGlobal('fetch', fn)
  return {
    calls,
    meCalls,
    /** Queue a reply for one /api/me/* URL (used once, then the default applies again). */
    route(url: string, status: number | 'network', body?: unknown) {
      ;(routes[url] ??= []).push(status === 'network' ? 'network' : { status, body })
    },
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
