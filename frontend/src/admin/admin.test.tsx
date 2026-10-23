import { act, fireEvent, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { AppRoutes } from '../App'
import { ToastHost } from '../components/ToastHost'
import { clearMemoryStorage } from '../lib/storage'
import { FakeWebSocket } from '../test/fakeWebSocket'
import { renderWithRoom } from '../test/render'
import type { AdminSession } from './api'
import { fmtDuration, fmtPct, niceMax } from './format'

// ----- a route-based fake backend ----------------------------------------------------

interface Call {
  path: string
  params: URLSearchParams
  method: string
  headers: Record<string, string>
}

let calls: Call[] = []
let routes: Record<string, (call: Call) => { status?: number; body: unknown }> = {}

function serve() {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init: RequestInit = {}) => {
      const parsed = new URL(url, 'http://localhost')
      const call = {
        path: parsed.pathname,
        params: parsed.searchParams,
        method: init.method ?? 'GET',
        headers: (init.headers ?? {}) as Record<string, string>,
      }
      calls.push(call)
      const handler = routes[`${call.method} ${call.path}`] ?? routes[call.path]
      if (!handler) return { ok: false, status: 404, json: async () => ({ error: { code: 'NOT_FOUND', message: 'nope' } }) }
      const { status = 200, body } = handler(call)
      return { ok: status < 400, status, json: async () => body } as Response
    }),
  )
}

const SESSION: AdminSession = {
  staff: true,
  username: 'boss',
  superuser: true,
  csrfToken: 'csrf-123',
  loginUrl: '/manage/login/',
  logoutUrl: '/manage/logout/',
  adminUrl: '/manage/',
  exports: { users: '/manage/dashboard/export/users.csv', sessions: '/manage/dashboard/export/sessions.csv' },
  timeZone: 'UTC',
  minGamesForRates: 5,
}

const RANGES = [
  { key: 'today', label: 'Today' },
  { key: '7d', label: 'Last 7 days' },
  { key: '30d', label: 'Last 30 days' },
  { key: 'all', label: 'All time' },
]

const days = (n: number) =>
  Array.from({ length: n }, (_, i) => ({ date: `2026-10-${String(i + 1).padStart(2, '0')}`, count: i === 3 ? 7 : i % 3 }))

function overview(range = '7d') {
  return {
    range: RANGES.find((r) => r.key === range),
    ranges: RANGES,
    sessions: { completed: 42, abandoned: 3, today: 5, avgPlayers: 3.25, avgDuration: 78, abandonRate: 3 / 45 },
    mostPlayed: { id: 'rps', name: 'Rock-Paper-Scissors', plays: 20 },
    users: { total: 12, new: 4 },
    guestsSeen: 30,
    active: { daily: 6, weekly: 15, monthly: 33 },
    perDay: days(30),
    live: [{ code: 'WXYZ', status: 'playing', game: 'Hangman Duel', players: 3, online: 2 }],
    cachedSeconds: 60,
  }
}

const alice = { kind: 'registered', userId: 7, guestKey: null, name: 'Alice' }
const carl = { kind: 'guest', userId: null, guestKey: 'c'.repeat(16), shortKey: 'cccccccc', name: 'Carl' }

function usersPage(page = 1) {
  return {
    page,
    numPages: 2,
    count: 3,
    pageSize: 2,
    query: { q: '', type: '', sort: 'games', dir: 'desc' },
    sorts: ['games', 'wins', 'win_rate', 'last_seen'],
    minGamesForRates: 5,
    results:
      page === 1
        ? [
            { ...alice, username: 'alice', firstSeen: '2026-10-01T10:00:00Z', lastSeen: '2026-10-23T12:00:00Z', games: 9, wins: 5, losses: 4, winRate: 5 / 9, favorite: { id: 'rps', name: 'Rock-Paper-Scissors' } },
            { ...carl, username: null, firstSeen: '2026-10-02T10:00:00Z', lastSeen: '2026-10-22T12:00:00Z', games: 6, wins: 2, losses: 4, winRate: 2 / 6, favorite: null },
          ]
        : [{ kind: 'registered', userId: 8, guestKey: null, name: 'Bob', username: 'bob', firstSeen: null, lastSeen: null, games: 3, wins: 3, losses: 0, winRate: null, favorite: null }],
  }
}

function aliceDetail(isActive = true) {
  return {
    actor: { ...alice, username: 'alice', joined: '2026-10-01T10:00:00Z', isActive },
    permissions: { change: true, delete: true },
    minGamesForRates: 5,
    totals: { games: 9, wins: 5, losses: 4, abandoned: 1, winRate: 5 / 9, firstGame: null, lastGame: null },
    perGame: [{ id: 'rps', name: 'Rock-Paper-Scissors', played: 6, wins: 4, losses: 2, winRate: 4 / 6, avgPlacement: 1.33 }],
    mostPlayed: { id: 'rps', name: 'Rock-Paper-Scissors' },
    mostWon: { id: 'rps', name: 'Rock-Paper-Scissors' },
    mostLost: { id: 'hangman', name: 'Hangman Duel' },
    recent: [{ startedAt: '2026-10-23T12:00:00Z', game: { id: 'rps', name: 'Rock-Paper-Scissors' }, status: 'completed', placement: 1, leftEarly: false, opponents: ['Carl'] }],
    coPlayers: [{ ...carl, shared: 6, ahead: 4, behind: 2 }],
    events: [{ id: 1, kind: 'login', label: 'Login', occurredAt: '2026-10-23T09:00:00Z', roomCode: '', game: null }],
  }
}

beforeEach(() => {
  FakeWebSocket.reset()
  calls = []
  routes = {
    '/api/admin/session': () => ({ body: SESSION }),
    '/api/admin/overview': (c) => ({ body: overview(c.params.get('range') ?? '7d') }),
    '/api/admin/users': (c) => ({ body: usersPage(Number(c.params.get('page') ?? 1)) }),
    '/api/admin/users/u/7': () => ({ body: aliceDetail() }),
  }
  serve()
})
afterEach(() => {
  vi.unstubAllGlobals()
  localStorage.clear()
  clearMemoryStorage()
})

function open(route: string) {
  return renderWithRoom(
    <>
      <AppRoutes />
      <ToastHost />
    </>,
    { route },
  )
}

const requests = (path: string) => calls.filter((c) => c.path === path)

// ----- tests -------------------------------------------------------------------------

describe('staff gate', () => {
  it('asks a non-staff visitor to log in, coming back to the same page', async () => {
    routes['/api/admin/session'] = () => ({ body: { ...SESSION, staff: false, username: null } })
    open('/admin/users?type=guest')
    const link = await screen.findByRole('link', { name: 'Log in as staff' })
    expect(link).toHaveAttribute('href', '/manage/login/?next=%2Fadmin%2Fusers%3Ftype%3Dguest')
    expect(requests('/api/admin/users')).toHaveLength(0)
  })

  it('sends the session cookie with every request', async () => {
    open('/admin')
    await screen.findByRole('heading', { name: 'Overview' })
    const fetchMock = vi.mocked(fetch)
    expect(fetchMock.mock.calls.every(([, init]) => (init as RequestInit).credentials === 'same-origin')).toBe(true)
  })

  it('a 401 on a data request re-checks the session and shows the login screen', async () => {
    let staff = true
    routes['/api/admin/session'] = () => ({ body: { ...SESSION, staff } })
    routes['/api/admin/overview'] = () => {
      staff = false
      return { status: 401, body: { error: { code: 'UNAUTHORIZED', message: 'Log in as staff.', loginUrl: '/manage/login/' } } }
    }
    open('/admin')
    expect(await screen.findByRole('link', { name: 'Log in as staff' })).toBeInTheDocument()
  })

  it('logs out through the Django admin and returns to the gate', async () => {
    let staff = true
    routes['/api/admin/session'] = () => ({ body: { ...SESSION, staff } })
    routes['POST /manage/logout/'] = () => {
      staff = false
      return { body: {} }
    }
    open('/admin')
    fireEvent.click(await screen.findByRole('button', { name: 'Log out' }))
    expect(await screen.findByRole('link', { name: 'Log in as staff' })).toBeInTheDocument()
    expect(calls.some((c) => c.method === 'POST' && c.path === '/manage/logout/')).toBe(true)
  })
})

describe('overview', () => {
  it('shows the key numbers, the chart, live rooms and navigation', async () => {
    open('/admin')
    expect(await screen.findByText('Registered users')).toBeInTheDocument()
    const stats = screen.getByRole('region', { name: 'Key numbers' })
    expect(within(stats).getByText('12')).toBeInTheDocument()
    expect(within(stats).getByText('4 new, last 7 days')).toBeInTheDocument()
    expect(within(stats).getByText('1m 18s')).toBeInTheDocument()
    expect(within(stats).getByText('7%')).toBeInTheDocument()
    expect(within(stats).getByRole('link', { name: 'Rock-Paper-Scissors' })).toHaveAttribute('href', '/admin/games/rps')
    expect(screen.getByText('WXYZ')).toBeInTheDocument()
    for (const name of ['Overview', 'Games', 'Users', 'Leaderboards', 'Activity']) {
      expect(screen.getByRole('link', { name })).toBeInTheDocument()
    }
    expect(screen.getByRole('link', { name: 'Django admin' })).toHaveAttribute('href', '/manage/')
  })

  it('changing the range refetches and keeps the old numbers on screen meanwhile', async () => {
    open('/admin')
    await screen.findByText('Registered users')
    fireEvent.click(screen.getByRole('radio', { name: 'All time' }))
    expect(document.querySelector('[aria-busy="true"]')).not.toBeNull()
    await waitFor(() => expect(screen.getByRole('radio', { name: 'All time' })).toHaveAttribute('aria-checked', 'true'))
    expect(requests('/api/admin/overview').map((c) => c.params.get('range'))).toEqual(['7d', 'all'])
  })

  it('chart columns show their value on focus and the table view lists every day', async () => {
    open('/admin')
    await screen.findByText('Registered users')
    const chart = screen.getByRole('group', { name: /Completed games per day/ })
    const column = within(chart).getByLabelText('Sun 4 Oct: 7 games')
    act(() => column.focus())
    expect(within(chart).getByRole('status')).toHaveTextContent('7')
    const figure = chart.closest('figure') as HTMLElement
    expect(within(figure).getByText('Show as table')).toBeInTheDocument()
    expect(within(figure).getAllByRole('row', { hidden: true })).toHaveLength(31) // header + 30 days
  })
})

describe('users', () => {
  it('lists players with badges, searches and pages through results', async () => {
    open('/admin/users')
    expect(await screen.findByRole('link', { name: 'Alice' })).toHaveAttribute('href', '/admin/users/u/7')
    expect(screen.getByRole('link', { name: 'Carl' })).toHaveAttribute('href', `/admin/users/g/${'c'.repeat(16)}`)
    expect(screen.getByText('guest cccccccc')).toBeInTheDocument()
    expect(screen.getByText('56%')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Export CSV' })).toHaveAttribute('href', SESSION.exports.users)

    fireEvent.change(screen.getByPlaceholderText('Nickname or username'), { target: { value: 'ali' } })
    fireEvent.click(screen.getByRole('button', { name: 'Search' }))
    await waitFor(() => expect(requests('/api/admin/users').at(-1)?.params.get('q')).toBe('ali'))

    fireEvent.click(screen.getByRole('button', { name: 'Next ›' }))
    expect(await screen.findByRole('link', { name: 'Bob' })).toBeInTheDocument()
    expect(requests('/api/admin/users').at(-1)?.params.get('page')).toBe('2')
  })
})

describe('user detail and actions', () => {
  it('shows totals, games, co-players and the timeline', async () => {
    open('/admin/users/u/7')
    expect(await screen.findByRole('heading', { name: 'Alice' })).toBeInTheDocument()
    const totals = screen.getByRole('region', { name: 'Totals' })
    expect(within(totals).getByText('Hangman Duel')).toBeInTheDocument() // most lost
    expect(screen.getByRole('link', { name: 'Carl' })).toBeInTheDocument()
    expect(screen.getByText('Login')).toBeInTheDocument()
  })

  it('disables with the CSRF token, then deletes after confirming', async () => {
    let active = true
    routes['/api/admin/users/u/7'] = () => ({ body: aliceDetail(active) })
    routes['POST /api/admin/users/u/7/disable'] = () => {
      active = false
      return { body: { ok: true, isActive: false } }
    }
    routes['POST /api/admin/users/u/7/delete'] = () => ({ body: { ok: true, deleted: true } })
    open('/admin/users/u/7')
    fireEvent.click(await screen.findByRole('button', { name: 'Disable account' }))
    expect(await screen.findByRole('button', { name: 'Enable account' })).toBeInTheDocument()
    const post = calls.find((c) => c.method === 'POST')
    expect(post?.headers['X-CSRFToken']).toBe('csrf-123')
    expect(screen.getByText('disabled')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Delete account' }))
    const dialog = screen.getByRole('dialog')
    expect(calls.filter((c) => c.path.endsWith('/delete'))).toHaveLength(0)
    fireEvent.click(within(dialog).getByRole('button', { name: 'Yes, delete the account' }))
    expect(await screen.findByText('Account deleted. Its games are kept as “Deleted player”.')).toBeInTheDocument()
    expect(await screen.findByRole('heading', { name: 'Users' })).toBeInTheDocument()
  })

  it('hides account actions without permission', async () => {
    routes['/api/admin/users/u/7'] = () => ({ body: { ...aliceDetail(), permissions: { change: false, delete: false } } })
    open('/admin/users/u/7')
    await screen.findByRole('heading', { name: 'Alice' })
    expect(screen.queryByRole('button', { name: /account/ })).not.toBeInTheDocument()
  })
})

describe('other pages', () => {
  it('games, leaderboards and activity load with their filters', async () => {
    routes['/api/admin/games'] = () => ({
      body: {
        range: RANGES[1],
        ranges: RANGES,
        games: [{ id: 'rps', name: 'Rock-Paper-Scissors', plays: 6, abandoned: 1, uniquePlayers: 2, avgPlayers: 2, avgDuration: 60, completionRate: 6 / 7 }],
      },
    })
    routes['/api/admin/leaderboards'] = (c) => ({
      body: {
        game: c.params.get('game') ? { id: 'rps', name: 'Rock-Paper-Scissors' } : null,
        games: [{ id: 'rps', name: 'Rock-Paper-Scissors' }],
        minGamesForRates: 5,
        mostWins: [{ ...alice, games: 9, wins: 5, winRate: null }],
        bestRate: [],
        mostGames: [{ ...carl, games: 6, wins: 2, winRate: null }],
      },
    })
    routes['/api/admin/activity'] = () => ({
      body: {
        page: 1,
        numPages: 1,
        count: 1,
        pageSize: 50,
        query: { kind: '', game: '', date: null },
        kinds: [{ value: 'login', label: 'Login' }],
        games: [{ id: 'rps', name: 'Rock-Paper-Scissors' }],
        results: [{ id: 1, kind: 'login', label: 'Login', occurredAt: '2026-10-23T09:00:00Z', who: alice, roomCode: '', game: null }],
      },
    })

    const games = open('/admin/games')
    expect(await screen.findByRole('link', { name: 'Rock-Paper-Scissors' })).toHaveAttribute('href', '/admin/games/rps?range=7d')
    expect(screen.getByText('86%')).toBeInTheDocument()
    games.unmount()

    const boards = open('/admin/leaderboards')
    expect(await screen.findByRole('region', { name: 'Most wins' })).toHaveTextContent('Alice')
    fireEvent.change(screen.getByLabelText('Game'), { target: { value: 'rps' } })
    await waitFor(() => expect(requests('/api/admin/leaderboards').at(-1)?.params.get('game')).toBe('rps'))
    boards.unmount()

    open('/admin/activity')
    expect(await screen.findByRole('link', { name: 'Alice' })).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Kind'), { target: { value: 'login' } })
    await waitFor(() => expect(requests('/api/admin/activity').at(-1)?.params.get('kind')).toBe('login'))
    expect(screen.getByRole('link', { name: 'Export game sessions CSV' })).toHaveAttribute('href', SESSION.exports.sessions)
  })
})

describe('format helpers', () => {
  it('formats durations, rates and axis tops', () => {
    expect(fmtDuration(78)).toBe('1m 18s')
    expect(fmtDuration(42)).toBe('42s')
    expect(fmtDuration(3725)).toBe('1h 02m')
    expect(fmtDuration(null)).toBe('—')
    expect(fmtPct(5 / 9)).toBe('56%')
    expect(fmtPct(null)).toBe('—')
    expect([0, 1, 3, 7, 12, 99, 101].map(niceMax)).toEqual([1, 1, 5, 10, 20, 100, 200])
  })
})
