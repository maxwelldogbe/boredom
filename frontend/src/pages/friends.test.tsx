import { act, fireEvent, screen, waitFor, within } from '@testing-library/react'
import { readFileSync } from 'node:fs'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { AppRoutes } from '../App'
import { ToastHost } from '../components/ToastHost'
import { adoptSession, clearAuthToken } from '../lib/account'
import { clearMemoryStorage } from '../lib/storage'
import { fakeFetch } from '../test/fakeFetch'
import { FakeWebSocket } from '../test/fakeWebSocket'
import { profileFx, socialFx } from '../test/fixtures'
import { renderWithRoom, saveTestProfile } from '../test/render'

let api: ReturnType<typeof fakeFetch>
const FRIENDS = '/api/friends'
const USERNAMES = [profileFx.me.profile.username, 'ann_social', 'bob_social', 'sam_social']

beforeEach(() => {
  FakeWebSocket.reset()
  api = fakeFetch()
})
afterEach(() => {
  vi.unstubAllGlobals()
  localStorage.clear()
  clearMemoryStorage()
})

function signIn() {
  adoptSession({ token: 'jwt-1', profile: profileFx.me.profile, stats: profileFx.me.stats })
}

async function settle() {
  await act(async () => {
    await Promise.resolve()
    await Promise.resolve()
  })
}

async function open(route = '/friends', overview: unknown = socialFx.overview, status = 200) {
  api.route(FRIENDS, status, overview)
  const view = renderWithRoom(
    <>
      <AppRoutes />
      <ToastHost />
    </>,
    { route },
  )
  await settle()
  return view
}

const friendRow = (name: string) => screen.getByText(name, { selector: '.friend-row__name' }).closest('li')!
const lastCall = () => api.calls.at(-1)!

// ----- guests ------------------------------------------------------------------------

describe('guests', () => {
  it('see a card to create an account, and nothing is sent for them', async () => {
    saveTestProfile()
    const { ws } = await open()
    expect(screen.getByRole('heading', { name: 'Create an account to add friends' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Create account' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Sign in' })).toBeInTheDocument()
    expect(ws.frames().map((f) => f.type)).not.toContain('auth:hello')
    expect(api.meCalls.filter((c) => c.url === FRIENDS)).toHaveLength(0)
  })

  it('Sign in opens the login form on the profile page', async () => {
    saveTestProfile()
    await open()
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(await screen.findByRole('tab', { name: 'Log in', selected: true })).toBeInTheDocument()
  })

  it('home shows a Friends button without a badge', async () => {
    saveTestProfile()
    await open('/')
    const link = screen.getByRole('link', { name: /Friends/ })
    expect(link).toHaveAttribute('href', '/friends')
    expect(link.querySelector('.count-badge')).toBeNull()
  })
})

// ----- connection --------------------------------------------------------------------

describe('auth:hello', () => {
  it('is the first frame after connecting and after every reconnect', async () => {
    signIn()
    const { ws } = await open('/')
    expect(ws.frames()[0]).toMatchObject({ type: 'auth:hello', payload: { authToken: 'jwt-1' } })
    ws.ack(socialFx.helloAck, ws.frames()[0].id)
    act(() => ws.drop())
    await act(async () => {
      await new Promise((r) => setTimeout(r, 600))
    })
    const next = FakeWebSocket.last()
    expect(next).not.toBe(ws)
    act(() => next.open())
    expect(next.frames()[0]).toMatchObject({ type: 'auth:hello', payload: { authToken: 'jwt-1' } })
  })

  it('reloads the friends list once hello is acknowledged, so nothing sent meanwhile is missed', async () => {
    signIn()
    const { ws } = await open('/')
    const loads = () => api.meCalls.filter((c) => c.url === FRIENDS).length
    const before = loads()
    api.route(FRIENDS, 200, { ...socialFx.overview, incoming: [...socialFx.overview.incoming, socialFx.requestPush.request] })
    ws.ack(socialFx.helloAck, ws.frames()[0].id)
    await settle()
    expect(loads()).toBe(before + 1)
    expect(within(screen.getByRole('link', { name: /Friends/ })).getByText('2')).toBeInTheDocument()
  })

  it('logging out re-sends hello without a token (signing the socket out)', async () => {
    signIn()
    const { ws } = await open('/')
    act(() => clearAuthToken())
    expect(ws.lastFrame()).toMatchObject({ type: 'auth:hello', payload: {} })
  })
})

// ----- home badge --------------------------------------------------------------------

describe('home', () => {
  it('shows the number of incoming requests and updates it live', async () => {
    signIn()
    const { ws } = await open('/')
    const link = await screen.findByRole('link', { name: /Friends/ })
    expect(within(link).getByText('1')).toBeInTheDocument()
    expect(link).toHaveAccessibleName('Friends, 1 new request')
    act(() => ws.receive({ type: 'friends:request', data: socialFx.requestPush }))
    expect(within(link).getByText('2')).toBeInTheDocument()
  })
})

// ----- the page ----------------------------------------------------------------------

describe('friends tab', () => {
  it('lists friends online first with icon and words for every status', async () => {
    signIn()
    await open()
    const rows = screen.getAllByText(/./, { selector: '.friend-row__name' }).map((e) => e.textContent)
    expect(rows).toEqual(['Ann', 'Bob', 'Cat'])
    for (const [name, label] of [
      ['Ann', 'Online'],
      ['Bob', 'In a lobby'],
      ['Cat', 'Offline'],
    ]) {
      const status = friendRow(name).querySelector('.status-label')!
      expect(status).toHaveTextContent(label)
      expect(status.querySelector('[aria-hidden="true"]')!.textContent).not.toBe('')
    }
    expect(within(friendRow('Ann')).getByText(`#${socialFx.tags.Ann}`)).toBeInTheDocument()
  })

  it('loading, error with retry, and empty states', async () => {
    signIn()
    api.route(FRIENDS, 500, { error: { code: 'SERVER', message: 'Boom.' } })
    api.route(FRIENDS, 200, socialFx.emptyOverview)
    renderWithRoom(<AppRoutes />, { route: '/friends' })
    expect(screen.getByRole('status')).toHaveTextContent('Loading your friends…')
    await settle()
    expect(screen.getByRole('alert')).toHaveTextContent('Boom.')
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }))
    await settle()
    expect(screen.getByRole('heading', { name: 'No friends yet' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('tab', { name: 'Requests' }))
    expect(screen.getByText('No requests right now.')).toBeInTheDocument()
    expect(screen.getByText('You have no requests waiting.')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('tab', { name: 'Blocked' }))
    expect(screen.getByRole('heading', { name: 'Nobody is blocked' })).toBeInTheDocument()
  })

  it('statuses change live from snapshot and presence pushes; removals drop the row', async () => {
    signIn()
    const { ws } = await open()
    const label = () => friendRow('Ann').querySelector('.status-label')!
    act(() => ws.receive({ type: 'friends:presence', data: socialFx.presenceBusy }))
    expect(label()).toHaveTextContent('Busy')
    expect(screen.getAllByText(/./, { selector: '.friend-row__name' }).map((e) => e.textContent)).toEqual([
      'Bob',
      'Ann',
      'Cat',
    ])
    act(() => ws.receive({ type: 'friends:presence', data: { tag: socialFx.tags.Ann, status: 'in_game' } }))
    expect(label()).toHaveTextContent('In a game')
    const snapshot = { friends: [{ tag: socialFx.tags.Ann, status: 'offline' }] }
    act(() => ws.receive({ type: 'friends:snapshot', data: snapshot }))
    expect(label()).toHaveTextContent('Offline')
    act(() => ws.receive({ type: 'friends:removed', data: socialFx.removedPush }))
    expect(screen.queryByText('Cat', { selector: '.friend-row__name' })).not.toBeInTheDocument()
  })

  it('friends:accepted reloads the list', async () => {
    signIn()
    const { ws } = await open()
    const withEve = {
      ...socialFx.overview,
      friends: [...socialFx.overview.friends, { ...socialFx.overview.outgoing[0], status: 'online' }],
      outgoing: [],
    }
    api.route(FRIENDS, 200, withEve)
    act(() => ws.receive({ type: 'friends:accepted', data: socialFx.acceptedPush }))
    await settle()
    expect(screen.getByText('Eve', { selector: '.friend-row__name' })).toBeInTheDocument()
  })

  it('never shows a login username', async () => {
    signIn()
    await open()
    for (const name of USERNAMES) expect(document.body.innerHTML).not.toContain(name)
  })
})

describe('add friend', () => {
  const input = () => screen.getByLabelText('Add a friend by tag')

  it('uppercases, accepts a pasted "#tag", and toasts "Request sent"', async () => {
    signIn()
    await open()
    fireEvent.change(input(), { target: { value: ' #k7m2qx9 ' } })
    expect(input()).toHaveValue('K7M2QX')
    api.reply(200, socialFx.requestSent)
    fireEvent.click(screen.getByRole('button', { name: 'Send' }))
    await settle()
    expect(lastCall()).toMatchObject({ method: 'POST', url: '/api/friends/requests', body: { tag: 'K7M2QX' } })
    expect(lastCall().headers.Authorization).toBe('Bearer jwt-1')
    expect(await screen.findByText('Request sent')).toBeInTheDocument()
    expect(input()).toHaveValue('')
  })

  it('auto-accepted requests say so', async () => {
    signIn()
    await open()
    fireEvent.change(input(), { target: { value: socialFx.tags.Dan } })
    api.reply(200, socialFx.acceptAck)
    fireEvent.click(screen.getByRole('button', { name: 'Send' }))
    expect(await screen.findByText("You're now friends!")).toBeInTheDocument()
  })

  it.each([
    ['NOT_FOUND', "We couldn't find a player with that tag. Check it and try again."],
    ['INVALID_INPUT', 'A tag is 6 letters and numbers, like #K7M2QX.'],
    ['SELF', "That's your own tag."],
    ['ALREADY_FRIENDS', "You're already friends."],
    ['ALREADY_REQUESTED', 'You already sent them a request.'],
    ['RATE_LIMITED', 'You sent a lot of requests. Try again in a while.'],
  ])('%s has a clear message', async (code, message) => {
    signIn()
    await open()
    const captured = socialFx.requestErrors[code]
    fireEvent.change(input(), { target: { value: 'ZZZZZZ' } })
    api.reply(captured.status, captured.body)
    fireEvent.click(screen.getByRole('button', { name: 'Send' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(message)
    expect(input()).toHaveAttribute('aria-invalid', 'true')
  })

  it('LIMIT_REACHED shows the server reason', async () => {
    signIn()
    await open()
    const captured = socialFx.requestErrors.LIMIT_REACHED
    fireEvent.change(input(), { target: { value: 'ZZZZZZ' } })
    api.reply(captured.status, captured.body)
    fireEvent.click(screen.getByRole('button', { name: 'Send' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(captured.body.error.message)
  })

  it('a short tag is caught before sending', async () => {
    signIn()
    await open()
    fireEvent.change(input(), { target: { value: 'AB' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send' }))
    expect(screen.getByRole('alert')).toHaveTextContent('A tag is 6 letters and numbers')
    expect(api.calls).toHaveLength(0)
  })
})

describe('friend menu', () => {
  const menu = (name: string) => within(friendRow(name)).getByRole('button', { name: `More for ${name}` })
  const choose = (name: string, item: string) => {
    fireEvent.click(menu(name))
    fireEvent.click(screen.getByRole('menuitem', { name: item }))
  }

  it('opens with the four actions, arrow keys move, Escape closes and returns focus', async () => {
    signIn()
    await open()
    fireEvent.click(menu('Ann'))
    const items = screen.getAllByRole('menuitem')
    expect(items.map((i) => i.textContent)).toEqual(['View profile', 'Remove friend', 'Block', 'Report'])
    expect(items[0]).toHaveFocus()
    fireEvent.keyDown(items[0], { key: 'ArrowDown' })
    expect(items[1]).toHaveFocus()
    fireEvent.keyDown(items[1], { key: 'Escape' })
    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
    expect(menu('Ann')).toHaveFocus()
  })

  it('View profile shows the friend stats cards', async () => {
    signIn()
    await open()
    api.reply(200, socialFx.friendProfile)
    choose('Ann', 'View profile')
    const dialog = screen.getByRole('dialog', { name: 'Ann' })
    await settle()
    expect(lastCall().url).toBe(`/api/friends/${socialFx.tags.Ann}/profile`)
    const totals = socialFx.friendProfile.stats.totals
    expect(within(dialog).getByText('Games').previousSibling).toHaveTextContent(String(totals.played))
    expect(within(dialog).getByText(/^Member since/)).toBeInTheDocument()
    expect(within(dialog).getByRole('heading', { name: 'By game' })).toBeInTheDocument()
  })

  it('View profile error offers a retry', async () => {
    signIn()
    await open()
    api.reply(403, socialFx.friendProfileForbidden)
    choose('Ann', 'View profile')
    await settle()
    const dialog = screen.getByRole('dialog', { name: 'Ann' })
    expect(within(dialog).getAllByRole('alert')[0]).toHaveTextContent('Only friends can see this profile.')
  })

  it('Remove asks first with focus on Cancel, then removes the row', async () => {
    signIn()
    await open()
    choose('Bob', 'Remove friend')
    const dialog = screen.getByRole('dialog', { name: 'Remove Bob?' })
    expect(within(dialog).getByRole('button', { name: 'Cancel' })).toHaveFocus()
    api.reply(200, { ok: true })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Remove friend' }))
    await settle()
    expect(lastCall()).toMatchObject({ method: 'DELETE', url: `/api/friends/${socialFx.tags.Bob}` })
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(screen.queryByText('Bob', { selector: '.friend-row__name' })).not.toBeInTheDocument()
  })

  it('Block asks first, then moves them to the Blocked tab', async () => {
    signIn()
    await open()
    choose('Ann', 'Block')
    const dialog = screen.getByRole('dialog', { name: 'Block Ann?' })
    expect(within(dialog).getByRole('button', { name: 'Cancel' })).toHaveFocus()
    api.reply(200, socialFx.blockAck)
    fireEvent.click(within(dialog).getByRole('button', { name: 'Block' }))
    await settle()
    expect(lastCall()).toMatchObject({ method: 'POST', url: '/api/blocks', body: { tag: socialFx.tags.Ann } })
    expect(screen.queryByText('Ann', { selector: '.friend-row__name' })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('tab', { name: 'Blocked' }))
    expect(screen.getByText('Ann', { selector: '.friend-row__name' })).toBeInTheDocument()
  })

  it('a failed block stays open with the error', async () => {
    signIn()
    await open()
    choose('Ann', 'Block')
    api.networkError()
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Block' }))
    await settle()
    expect(within(screen.getByRole('dialog')).getByRole('alert')).toHaveTextContent("Can't reach the server")
  })

  it('Report needs a reason, counts the note, and sends both', async () => {
    signIn()
    await open()
    choose('Cat', 'Report')
    const dialog = screen.getByRole('dialog', { name: 'Report Cat' })
    expect(within(dialog).getByRole('button', { name: 'Cancel' })).toHaveFocus()
    const send = within(dialog).getByRole('button', { name: 'Send report' })
    expect(send).toBeDisabled()
    const radios = within(dialog).getAllByRole('radio')
    expect(radios.map((r) => r.closest('label')!.textContent)).toEqual([
      'Harassment or bullying',
      'Inappropriate name or avatar',
      'Cheating',
      'Spam',
      'Something else',
    ])
    fireEvent.click(within(dialog).getByLabelText('Cheating'))
    const note = within(dialog).getByLabelText('Anything else? (optional)')
    expect(note).toHaveAttribute('maxLength', '200')
    fireEvent.change(note, { target: { value: 'kept peeking' } })
    expect(within(dialog).getByText('12/200')).toBeInTheDocument()
    api.reply(200, { ok: true })
    fireEvent.click(send)
    await settle()
    expect(lastCall()).toMatchObject({
      method: 'POST',
      url: '/api/reports',
      body: { tag: socialFx.tags.Cat, reason: 'cheating', note: 'kept peeking' },
    })
    expect(await screen.findByText('Thanks. Our team will take a look.')).toBeInTheDocument()
  })
})

describe('requests and blocked tabs', () => {
  it('accept, decline and cancel', async () => {
    signIn()
    await open('/friends?tab=requests')
    expect(screen.getByRole('tab', { name: /Requests/, selected: true })).toBeInTheDocument()
    const dan = socialFx.overview.incoming[0]
    api.reply(200, socialFx.acceptAck)
    api.route(FRIENDS, 200, { ...socialFx.overview, incoming: [] })
    fireEvent.click(screen.getByRole('button', { name: 'Accept Dan' }))
    await settle()
    expect(api.calls[0]).toMatchObject({ method: 'POST', url: `/api/friends/requests/${dan.requestId}/accept` })
    expect(await screen.findByText('You and Dan are now friends!')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Accept Dan' })).not.toBeInTheDocument()

    const eve = socialFx.overview.outgoing[0]
    api.reply(200, { ok: true })
    fireEvent.click(screen.getByRole('button', { name: 'Cancel request to Eve' }))
    await settle()
    expect(api.calls[1]).toMatchObject({ method: 'DELETE', url: `/api/friends/requests/${eve.requestId}` })
    expect(screen.getByText('You have no requests waiting.')).toBeInTheDocument()
  })

  it('decline removes the request', async () => {
    signIn()
    await open('/friends?tab=requests')
    api.reply(200, { ok: true })
    fireEvent.click(screen.getByRole('button', { name: 'Decline Dan' }))
    await settle()
    expect(api.calls[0].url).toBe(`/api/friends/requests/${socialFx.overview.incoming[0].requestId}/decline`)
    expect(screen.getByText('No requests right now.')).toBeInTheDocument()
  })

  it('a request arriving live shows up in the tab and its count', async () => {
    signIn()
    const { ws } = await open('/friends?tab=requests')
    act(() => ws.receive({ type: 'friends:request', data: socialFx.requestPush }))
    expect(screen.getByRole('button', { name: 'Accept Nia' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /Requests/ })).toHaveTextContent('2')
  })

  it('unblock', async () => {
    signIn()
    await open('/friends?tab=blocked')
    api.reply(200, { ok: true })
    fireEvent.click(screen.getByRole('button', { name: 'Unblock Zed' }))
    await settle()
    expect(api.calls[0]).toMatchObject({ method: 'DELETE', url: `/api/blocks/${socialFx.tags.Zed}` })
    expect(screen.getByRole('heading', { name: 'Nobody is blocked' })).toBeInTheDocument()
  })

  it('tabs move with the arrow keys', async () => {
    signIn()
    await open()
    const friends = screen.getByRole('tab', { name: 'Friends' })
    fireEvent.keyDown(friends, { key: 'ArrowRight' })
    expect(screen.getByRole('tab', { name: /Requests/ })).toHaveAttribute('aria-selected', 'true')
    fireEvent.keyDown(friends, { key: 'ArrowLeft' })
    expect(screen.getByRole('tab', { name: 'Friends' })).toHaveAttribute('aria-selected', 'true')
  })
})

describe('status setting', () => {
  it('shows the saved choice with a hint each and saves a change at once', async () => {
    signIn()
    const { ws } = await open()
    ws.ack(socialFx.helloAck, ws.frames()[0].id)
    await settle()
    const group = screen.getByRole('radiogroup', { name: 'Your status' })
    const options = within(group).getAllByRole('radio')
    expect(options.map((o) => o.querySelector('.presence__label')!.textContent)).toEqual([
      'Online',
      'Busy',
      'Appear offline',
    ])
    for (const o of options) expect(o.querySelector('.presence__hint')!.textContent).not.toBe('')
    expect(within(group).getByRole('radio', { name: /^Online/ })).toHaveAttribute('aria-checked', 'true')
    api.route('/api/me/settings', 200, socialFx.settingsBusy)
    fireEvent.click(within(group).getByRole('radio', { name: /^Busy/ }))
    await settle()
    const patch = api.meCalls.filter((c) => c.method === 'PATCH')
    expect(patch).toMatchObject([{ url: '/api/me/settings', body: { presence: 'busy' } }])
    expect(within(group).getByRole('radio', { name: /^Busy/ })).toHaveAttribute('aria-checked', 'true')
  })

  it('a failed save goes back to the previous choice', async () => {
    signIn()
    const { ws } = await open()
    ws.ack(socialFx.helloAck, ws.frames()[0].id)
    await settle()
    api.route('/api/me/settings', 'network')
    fireEvent.click(screen.getByRole('radio', { name: /^Appear offline/ }))
    await settle()
    expect(screen.getByRole('radio', { name: /^Online/ })).toHaveAttribute('aria-checked', 'true')
    expect(await screen.findByRole('alert')).toHaveTextContent("Can't reach the server")
  })

  it('without a hello yet, it reads the setting over HTTP', async () => {
    signIn()
    api.route('/api/me/settings', 200, socialFx.settingsBusy)
    await open()
    await waitFor(() => expect(screen.getByRole('radio', { name: /^Busy/ })).toHaveAttribute('aria-checked', 'true'))
  })
})

// ----- recent players on /profile ----------------------------------------------------

describe('recent players actions', () => {
  async function openProfile() {
    signIn()
    api.reply(200, profileFx.me)
    api.route('/api/me/recent-players', 200, socialFx.recentPlayers)
    await open('/profile')
    await screen.findByRole('heading', { level: 1, name: profileFx.me.profile.nickname })
    await settle()
  }
  const card = (name: string) =>
    within(screen.getByRole('region', { name: 'Recent players' })).getByRole('button', { name: new RegExp(`^${name} `) })

  it('Add friend sends a request and then says "Request sent"', async () => {
    await openProfile()
    fireEvent.click(card('Kim'))
    const dialog = screen.getByRole('dialog', { name: 'Kim' })
    api.reply(200, socialFx.requestSent)
    fireEvent.click(within(dialog).getByRole('button', { name: 'Add friend' }))
    await settle()
    const kim = socialFx.recentPlayers.players.find((p) => p.nickname === 'Kim')!
    expect(lastCall()).toMatchObject({ url: '/api/friends/requests', body: { tag: kim.tag } })
    expect(within(dialog).getByRole('button', { name: 'Request sent' })).toBeDisabled()
  })

  it('friends show a label, incoming requests offer Respond', async () => {
    await openProfile()
    fireEvent.click(card('Eve'))
    expect(within(screen.getByRole('dialog', { name: 'Eve' })).getByText('Friends')).toBeInTheDocument()
    fireEvent.keyDown(document, { key: 'Escape' })
    fireEvent.click(card('Dan'))
    fireEvent.click(within(screen.getByRole('dialog', { name: 'Dan' })).getByRole('button', { name: 'Respond to their request' }))
    expect(await screen.findByRole('tab', { name: /Requests/, selected: true })).toBeInTheDocument()
  })

  it('Block asks first and hides the player; Report sends a report', async () => {
    await openProfile()
    fireEvent.click(card('Kim'))
    fireEvent.click(within(screen.getByRole('dialog', { name: 'Kim' })).getByRole('button', { name: 'Block' }))
    const confirm = screen.getByRole('dialog', { name: 'Block Kim?' })
    expect(within(confirm).getByRole('button', { name: 'Cancel' })).toHaveFocus()
    api.reply(200, socialFx.blockAck)
    fireEvent.click(within(confirm).getByRole('button', { name: 'Block' }))
    await settle()
    expect(screen.queryByRole('button', { name: /^Kim / })).not.toBeInTheDocument()
    fireEvent.click(card('Nia'))
    fireEvent.click(within(screen.getByRole('dialog', { name: 'Nia' })).getByRole('button', { name: 'Report' }))
    const report = screen.getByRole('dialog', { name: 'Report Nia' })
    fireEvent.click(within(report).getByLabelText('Spam'))
    api.reply(200, { ok: true })
    fireEvent.click(within(report).getByRole('button', { name: 'Send report' }))
    await settle()
    expect(lastCall()).toMatchObject({ url: '/api/reports', body: { reason: 'spam' } })
  })

  it('shows what we save on the profile page', async () => {
    await openProfile()
    const note = screen.getByRole('region', { name: 'What we save' })
    expect(note).toHaveTextContent('Your friends, friend requests and the players you block.')
    expect(note).toHaveTextContent('Only our team sees them.')
  })
})

describe('layout', () => {
  it('320px: rows wrap, the status control stacks, and every control is tall enough', () => {
    const css = readFileSync('src/styles/social.css', 'utf8')
    const rule = (name: string) => css.match(new RegExp(`\\.${name} \\{([^}]*)\\}`))![1]
    expect(rule('friend-row')).toMatch(/flex-wrap: wrap/)
    expect(rule('friend-row__name')).toMatch(/text-overflow: ellipsis/)
    expect(rule('add-friend__input')).toMatch(/min-width: 0/)
    expect(rule('presence__options')).toMatch(/repeat\(auto-fit, minmax\(128px, 1fr\)\)/)
    for (const name of ['menu__button', 'menu__item', 'presence__option', 'report__reason']) {
      expect(rule(name)).toMatch(/min-height: var\(--tap\)/)
    }
    expect(css).toMatch(/\.friends \.tabs__tab \{[^}]*min-height: var\(--tap\)/)
    for (const [, body] of css.matchAll(/\{([^}]*)\}/g)) expect(body).not.toMatch(/(^|\s)width: \d{3,}px/)
  })
})
