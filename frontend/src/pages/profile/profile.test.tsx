import { act, fireEvent, screen, within } from '@testing-library/react'
import { readFileSync } from 'node:fs'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { AppRoutes } from '../../App'
import { ToastHost } from '../../components/ToastHost'
import { GAME_UIS } from '../../games/registry'
import { adoptSession } from '../../lib/account'
import { clearMemoryStorage } from '../../lib/storage'
import { fakeFetch } from '../../test/fakeFetch'
import { FakeWebSocket } from '../../test/fakeWebSocket'
import { profileFx } from '../../test/fixtures'
import { renderWithRoom, saveTestProfile } from '../../test/render'

let api: ReturnType<typeof fakeFetch>
const STATS = '/api/me/stats'
const RECENT = '/api/me/recent-players'
const USERNAME = profileFx.me.profile.username

beforeEach(() => {
  FakeWebSocket.reset()
  api = fakeFetch()
})
afterEach(() => {
  vi.unstubAllGlobals()
  localStorage.clear()
  clearMemoryStorage()
})

/** Open /profile as Sam (registered) with the captured replies, unless overridden. */
async function openProfile({
  me = profileFx.me,
  stats = profileFx.stats as unknown,
  recent = profileFx.recentPlayers as unknown,
  statsStatus = 200,
  recentStatus = 200,
} = {}) {
  adoptSession({ token: 'jwt-1', profile: me.profile, stats: me.stats })
  api.reply(200, me)
  api.route(STATS, statsStatus, stats)
  api.route(RECENT, recentStatus, recent)
  const view = renderWithRoom(
    <>
      <AppRoutes />
      <ToastHost />
    </>,
    { route: '/profile' },
  )
  await screen.findByRole('heading', { level: 1, name: me.profile.nickname })
  await act(async () => {
    await Promise.resolve()
  })
  return view
}

const section = (name: string) => screen.getByRole('region', { name })

describe('header', () => {
  it('shows the avatar in a ring of the profile color, the tag and the month joined', async () => {
    await openProfile()
    const header = screen.getByRole('banner')
    expect(within(header).getByText(`#${profileFx.me.tag}`)).toBeInTheDocument()
    expect(within(header).getByText('Member since October 2026')).toBeInTheDocument()
    const ring = header.querySelector<HTMLElement>('.ring-avatar')!
    expect(ring.style.getPropertyValue('--ring-size')).toBe('96px')
    expect(ring.style.borderColor).not.toBe('')
  })

  it('copies the tag with a toast', async () => {
    const writeText = vi.fn(async () => {})
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
    Object.defineProperty(window, 'isSecureContext', { value: true, configurable: true })
    await openProfile()
    fireEvent.click(within(screen.getByRole('banner')).getByRole('button', { name: 'Copy tag' }))
    expect(await screen.findByText('Tag copied')).toBeInTheDocument()
    expect(writeText).toHaveBeenCalledWith(`#${profileFx.me.tag}`)
  })

  it('never shows the login username, nor the old "Logged in as" line', async () => {
    await openProfile()
    expect(document.body.innerHTML).not.toContain(USERNAME)
    expect(screen.queryByText(/Logged in as/)).not.toBeInTheDocument()
  })

  it('an older server without a tag still renders the page', async () => {
    const old = { profile: profileFx.me.profile, stats: profileFx.me.stats }
    await openProfile({ me: old })
    expect(within(screen.getByRole('banner')).queryByText(/^#/)).not.toBeInTheDocument()
    expect(section('Stats')).toBeInTheDocument()
  })
})

describe('stats', () => {
  it('shows four cards from the server numbers, and the favorite game', async () => {
    await openProfile()
    const stats = section('Stats')
    const cards = within(stats).getAllByRole('listitem').map((li) => li.textContent)
    expect(cards).toEqual(['7Games', '4Wins', '3Losses', '57%Win rate'])
    expect(within(stats).getByText(/Favorite game/)).toHaveTextContent('Favorite game: ✊ Rock-Paper-Scissors')
  })

  it('a null win rate shows a dash and when it will appear', async () => {
    const stats = { ...profileFx.stats, totals: { ...profileFx.stats.totals, winRate: null } }
    await openProfile({ stats })
    const rate = within(section('Stats')).getAllByRole('listitem')[3]
    expect(rate).toHaveTextContent('—')
    expect(rate).toHaveTextContent(`Win rate shows after ${profileFx.stats.minGamesForRate} games`)
  })

  it('hides the favorite game when there is none', async () => {
    await openProfile({ stats: { ...profileFx.stats, favoriteGame: null } })
    expect(within(section('Stats')).queryByText(/Favorite game/)).not.toBeInTheDocument()
  })

  it('empty state before any game', async () => {
    await openProfile({ me: profileFx.newMe, stats: profileFx.statsEmpty, recent: profileFx.recentEmpty })
    expect(within(section('Stats')).getByText('Play a game to see your stats here')).toBeInTheDocument()
    expect(within(section('By game')).getByText('Play a game to see your stats here')).toBeInTheDocument()
    expect(within(section('Stats')).queryByRole('listitem')).not.toBeInTheDocument()
  })
})

describe('by game', () => {
  it('one row per game, named from the game registry', async () => {
    const perGame = [
      profileFx.stats.perGame[0],
      { gameId: 'liars_dice', played: 3, wins: 1, losses: 2, winRate: null },
      { gameId: 'hangman', played: 2, wins: 2, losses: 0, winRate: null },
    ]
    await openProfile({ stats: { ...profileFx.stats, perGame } })
    const rows = within(section('By game')).getAllByRole('listitem')
    expect(rows).toHaveLength(3)
    expect(rows[0]).toHaveTextContent(`${GAME_UIS.rps.name}7 played4 won57%`)
    expect(rows[1]).toHaveTextContent(`${GAME_UIS.liars_dice.name}3 played1 won—`)
    expect(rows[2]).toHaveTextContent(GAME_UIS.hangman.name)
  })
})

describe('recent players', () => {
  it('lists the players with ring avatar, tag and the two lines, newest first', async () => {
    await openProfile()
    const cards = within(section('Recent players')).getAllByRole('button')
    expect(cards.map((c) => c.querySelector('.recent__name')!.textContent)).toEqual([
      `Bob #${profileFx.recentPlayers.players[0].tag}`,
      `Ann #${profileFx.recentPlayers.players[1].tag}`,
    ])
    expect(cards[0]).toHaveTextContent('Played together 1 time')
    expect(cards[1]).toHaveTextContent('Played together 6 times')
    expect(cards[1]).toHaveTextContent(/Last played (now|\d+ (minute|hour|day)s? ago|yesterday)/)
    expect(cards[0].querySelector<HTMLElement>('.ring-avatar')!.style.getPropertyValue('--ring-size')).toBe('48px')
  })

  it('tapping a card opens a small modal with their details only, focus trapped', async () => {
    await openProfile()
    const ann = profileFx.recentPlayers.players[1]
    fireEvent.click(within(section('Recent players')).getAllByRole('button')[1])
    const dialog = screen.getByRole('dialog', { name: 'Ann' })
    expect(within(dialog).getByText(`#${ann.tag}`)).toBeInTheDocument()
    expect(within(dialog).getByRole('button', { name: 'Copy tag' })).toBeInTheDocument()
    expect(within(dialog).getByText('Played together 6 times')).toBeInTheDocument()
    expect(within(dialog).getByText(/^Last played/)).toBeInTheDocument()
    expect(within(dialog).getAllByRole('button').map((b) => b.textContent)).toEqual(['Copy', 'Close'])
    expect(dialog.textContent).not.toMatch(/won|Win rate|\d+ played/)

    const copy = within(dialog).getByRole('button', { name: 'Copy tag' })
    const close = within(dialog).getByRole('button', { name: 'Close' })
    expect(copy).toHaveFocus()
    close.focus()
    fireEvent.keyDown(document, { key: 'Tab' })
    expect(copy).toHaveFocus()
    fireEvent.keyDown(document, { key: 'Tab', shiftKey: true })
    expect(close).toHaveFocus()
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('empty state', async () => {
    await openProfile({ recent: profileFx.recentEmpty })
    expect(within(section('Recent players')).getByText('Players you play with will show up here')).toBeInTheDocument()
  })

  it('no usernames from the recent players reach the page', async () => {
    await openProfile()
    for (const name of ['ann_proof', 'bob_proof', 'sam_proof']) expect(document.body.innerHTML).not.toContain(name)
  })
})

describe('each section fails on its own', () => {
  it('a failed recent-players request shows Retry there and leaves the stats alone', async () => {
    await openProfile({ recentStatus: 500, recent: { error: { code: 'SERVER', message: 'Server error.' } } })
    const recent = section('Recent players')
    expect(within(recent).getByRole('alert')).toHaveTextContent('Server error.')
    expect(within(section('Stats')).getAllByRole('listitem')).toHaveLength(4)
    api.route(RECENT, 200, profileFx.recentPlayers)
    fireEvent.click(within(recent).getByRole('button', { name: 'Retry' }))
    expect(await within(recent).findByText(/^Ann/)).toBeInTheDocument()
  })

  it('a failed stats request shows Retry there and leaves recent players alone', async () => {
    await openProfile({ statsStatus: 500, stats: { error: { code: 'SERVER', message: 'Server error.' } } })
    expect(within(section('Stats')).getByRole('alert')).toBeInTheDocument()
    expect(within(section('By game')).getByRole('alert')).toBeInTheDocument()
    expect(within(section('Recent players')).getAllByRole('button')).toHaveLength(2)
    api.route(STATS, 200, profileFx.stats)
    fireEvent.click(within(section('Stats')).getByRole('button', { name: 'Retry' }))
    expect(await within(section('Stats')).findByText('Games')).toBeInTheDocument()
  })

  it('shows loading skeletons while the requests are in flight', () => {
    adoptSession({ token: 'jwt-1', profile: profileFx.me.profile, stats: profileFx.me.stats })
    api.reply(200, profileFx.me)
    renderWithRoom(<AppRoutes />, { route: '/profile' })
    expect(screen.getByRole('status', { name: 'Loading your stats' })).toBeInTheDocument()
    expect(screen.getByRole('status', { name: 'Loading recent players' })).toBeInTheDocument()
    expect(screen.getByRole('status', { name: 'Loading your tag' })).toBeInTheDocument()
  })

  it('an expired login on any request falls back to the guest page', async () => {
    adoptSession({ token: 'jwt-1', profile: profileFx.me.profile, stats: profileFx.me.stats })
    api.reply(200, profileFx.me)
    api.route(STATS, 401, profileFx.unauthorized)
    renderWithRoom(<AppRoutes />, { route: '/profile' })
    expect(await screen.findByRole('region', { name: 'Save your profile' })).toBeInTheDocument()
  })
})

describe('guests', () => {
  it('see the page exactly as before, and nothing is fetched', () => {
    saveTestProfile('Sam')
    renderWithRoom(<AppRoutes />, { route: '/profile' })
    expect(screen.getByRole('heading', { level: 1, name: 'Your profile' })).toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'Save your profile' })).toBeInTheDocument()
    expect(screen.queryByRole('region', { name: 'Stats' })).not.toBeInTheDocument()
    expect(screen.queryByRole('region', { name: 'Recent players' })).not.toBeInTheDocument()
    expect(api.meCalls).toHaveLength(0)
    expect(api.calls).toHaveLength(0)
  })
})

describe('layout', () => {
  it('320px: grids shrink instead of scrolling sideways, and the modal fits', () => {
    const pages = readFileSync('src/styles/pages.css', 'utf8')
    const components = readFileSync('src/styles/components.css', 'utf8')
    expect(pages).toMatch(/\.stat-cards \{[^}]*grid-template-columns: repeat\(2, minmax\(0, 1fr\)\)/)
    for (const rule of ['stat-card', 'bygame__row', 'recent__card', 'tag-chip', 'profile__header']) {
      const body = pages.match(new RegExp(`\\.${rule} \\{([^}]*)\\}`))![1]
      expect(body).not.toMatch(/(^|\s)(min-width: [1-9]|width: \d{3,}px)/)
    }
    expect(pages).toMatch(/\.bygame__row \{[^}]*flex-wrap: wrap/)
    expect(pages).toMatch(/\.recent__name \{[^}]*text-overflow: ellipsis/)
    expect(components).toMatch(/\.modal__box \{[^}]*width: 100%;[^}]*max-width: 420px/)
  })
})

describe('avatar shuffle', () => {
  const DAY = 24 * 3600 * 1000
  const picker = () => screen.getByRole('group', { name: 'Avatar' })
  const pickerImg = () => picker().querySelector('img')!.getAttribute('src')
  const savedSeed = profileFx.me.profile.avatar.seed
  const lockedMe = (until: number) => ({ ...profileFx.me, profile: { ...profileFx.me.profile, avatarLockedUntil: until } })
  const patchBody = () => api.calls.filter((c) => c.method === 'PATCH').at(-1)?.body as Record<string, unknown>

  it('shuffles until the player likes one, can go back, and saving starts the lock', async () => {
    await openProfile()
    expect(pickerImg()).toContain(`seed=${savedSeed}`)
    expect(within(picker()).getByText(/You can change it once every 30 days/)).toBeInTheDocument()
    fireEvent.click(within(picker()).getByRole('button', { name: 'Shuffle avatar' }))
    const first = pickerImg()
    expect(first).not.toContain(`seed=${savedSeed}`)
    fireEvent.click(within(picker()).getByRole('button', { name: 'Shuffle avatar' }))
    expect(pickerImg()).not.toBe(first)
    expect(within(picker()).getByText(/You can't change it again for 30 days/)).toBeInTheDocument()

    fireEvent.click(within(picker()).getByRole('button', { name: 'Keep my current one' }))
    expect(pickerImg()).toContain(`seed=${savedSeed}`)

    fireEvent.click(within(picker()).getByRole('button', { name: 'Shuffle avatar' }))
    const chosen = pickerImg()!
    const until = Date.now() + 30 * DAY
    const seed = new URL(chosen).searchParams.get('seed')!
    const style = new URL(chosen).pathname.split('/')[2]
    api.reply(200, { profile: { ...profileFx.me.profile, avatar: { style, seed }, avatarLockedUntil: until } })
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))
    expect(await screen.findByText('Profile saved. Enjoy your new avatar!')).toBeInTheDocument()
    expect(patchBody().avatar).toEqual({ style, seed })
    expect(within(picker()).queryByRole('button', { name: 'Shuffle avatar' })).not.toBeInTheDocument()
    expect(within(picker()).getByText(/You can change your avatar again on/)).toBeInTheDocument()
    expect(screen.getByRole('banner').querySelector('img')!.getAttribute('src')).toBe(chosen)
  })

  it('saving without shuffling sends no avatar', async () => {
    await openProfile()
    api.reply(200, { profile: profileFx.me.profile })
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))
    expect(await screen.findByText('Profile saved.')).toBeInTheDocument()
    expect(patchBody()).not.toHaveProperty('avatar')
  })

  it('while locked there is no shuffle, only the date it unlocks', async () => {
    const until = Date.UTC(2099, 10, 26, 12)
    await openProfile({ me: lockedMe(until) })
    expect(within(picker()).queryByRole('button', { name: 'Shuffle avatar' })).not.toBeInTheDocument()
    expect(within(picker()).getByText('You can change your avatar again on November 26, 2099.')).toBeInTheDocument()
  })

  it('a lock that has already passed allows shuffling', async () => {
    await openProfile({ me: lockedMe(Date.now() - DAY) })
    expect(within(picker()).getByRole('button', { name: 'Shuffle avatar' })).toBeInTheDocument()
  })

  it('a server refusal (changed on another device) shows why and reloads the real lock', async () => {
    await openProfile()
    fireEvent.click(within(picker()).getByRole('button', { name: 'Shuffle avatar' }))
    const message = 'You can change your avatar once every 30 days.'
    api.reply(409, { error: { code: 'AVATAR_LOCKED', message, fields: { avatar: message } } })
    api.reply(200, lockedMe(Date.now() + 10 * DAY))
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))
    expect(await screen.findByText(new RegExp(message))).toBeInTheDocument()
    expect(await screen.findByText(/You can change your avatar again on/)).toBeInTheDocument()
    expect(pickerImg()).toContain(`seed=${savedSeed}`)
  })
})
