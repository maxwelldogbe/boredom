import { act, fireEvent, screen, within } from '@testing-library/react'
import { readFileSync } from 'node:fs'
import { useEffect } from 'react'
import { useNavigate, type NavigateFunction } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { AppRoutes } from '../App'
import { InviteBanners } from '../components/Invites'
import { ToastHost } from '../components/ToastHost'
import { adoptSession } from '../lib/account'
import { C } from '../lib/constants'
import { clearMemoryStorage } from '../lib/storage'
import { fakeFetch } from '../test/fakeFetch'
import { FakeWebSocket } from '../test/fakeWebSocket'
import { profileFx, socialFx } from '../test/fixtures'
import { renderWithRoom, saveTestProfile } from '../test/render'
import type { RoomPublic } from '../types/protocol'

let api: ReturnType<typeof fakeFetch>
let go: NavigateFunction
const FRIENDS = '/api/friends'
const ROOM = socialFx.roomWithAccounts
const ann = socialFx.overview.friends.find((f) => f.nickname === 'Ann')!

beforeEach(() => {
  FakeWebSocket.reset()
  api = fakeFetch()
})
afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
  localStorage.clear()
  clearMemoryStorage()
})

function signIn() {
  adoptSession({ token: 'jwt-1', profile: profileFx.me.profile, stats: profileFx.me.stats })
}

async function settle() {
  await act(async () => {
    for (let i = 0; i < 4; i++) await Promise.resolve()
  })
}

function Nav() {
  const navigate = useNavigate()
  useEffect(() => {
    go = navigate
  }, [navigate])
  return null
}

async function open(route = '/', overview: unknown = socialFx.overview) {
  api.route(FRIENDS, 200, overview)
  api.route(FRIENDS, 200, overview) // reloaded once hello is acknowledged
  const view = renderWithRoom(
    <>
      <Nav />
      <InviteBanners />
      <AppRoutes />
      <ToastHost />
    </>,
    { route },
  )
  await settle()
  if (view.ws.frames()[0]?.type === 'auth:hello') view.ws.ack(socialFx.helloAck, view.ws.frames()[0].id)
  await settle()
  return view
}

const frame = (ws: FakeWebSocket, type: string) => ws.frames().filter((f) => f.type === type).at(-1)

/** Home → Create room → the lobby of ROOM (as Sam, or as a guest seat). */
async function intoLobby(ws: FakeWebSocket, room: RoomPublic = ROOM) {
  fireEvent.click(screen.getByRole('button', { name: 'Create room' }))
  await settle()
  ws.ack({ playerId: socialFx.roomSeats.sam, roomToken: 'tok', room }, frame(ws, 'room:create')!.id)
  await settle()
}

const friendRow = (name: string) => screen.getByText(name, { selector: '.friend-row__name' }).closest('li')!

// ----- guests -------------------------------------------------------------------------

describe('guests', () => {
  it('see no invite buttons, sections or banners anywhere', async () => {
    saveTestProfile()
    const { ws } = await open('/')
    act(() => ws.receive({ type: 'invite:received', data: socialFx.inviteReceived }))
    expect(screen.queryByText(/invited you to play/)).not.toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Friends online' })).not.toBeInTheDocument()
    const guestRoom = { ...ROOM, players: [{ ...ROOM.players[0], type: 'guest' as const }] }
    await intoLobby(ws, guestRoom)
    expect(screen.getByText('Room code')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Invite friends/ })).not.toBeInTheDocument()
    expect(ws.frames().map((f) => f.type)).not.toContain('invite:send')
  })
})

// ----- lobby --------------------------------------------------------------------------

describe('lobby "Invite friends"', () => {
  it('sits right under the room code and keeps the link and share options', async () => {
    signIn()
    const { ws } = await open('/')
    await intoLobby(ws)
    const button = screen.getByRole('button', { name: /Invite friends/ })
    expect(button.previousElementSibling).toHaveClass('lobby__code')
    expect(button).toHaveClass('invite-friends')
    expect(screen.getByRole('button', { name: 'Copy link' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Send on WhatsApp' })).toBeInTheDocument()
  })

  it('the sheet lists friends online first; only online ones can be invited; "Sent" lasts the cooldown', async () => {
    signIn()
    const { ws } = await open('/')
    await intoLobby(ws)
    vi.useFakeTimers({ toFake: ['Date', 'setInterval'] })
    fireEvent.click(screen.getByRole('button', { name: /Invite friends/ }))
    const sheet = screen.getByRole('dialog', { name: 'Invite friends' })
    expect(sheet.parentElement).toHaveClass('modal--sheet')
    const names = within(sheet).getAllByText(/./, { selector: '.friend-row__name' }).map((e) => e.textContent)
    expect(names).toEqual(['Ann', 'Bob', 'Cat'])
    expect(within(friendRow('Ann')).getByText('Online')).toBeInTheDocument()
    expect(within(friendRow('Bob')).getByRole('button', { name: 'Unavailable' })).toBeDisabled()
    expect(within(friendRow('Cat')).getByRole('button', { name: 'Unavailable' })).toBeDisabled()
    expect(sheet).not.toHaveTextContent(/lobby.*can't|offline.*can't/i)

    fireEvent.click(within(sheet).getByRole('button', { name: 'Invite Ann' }))
    expect(ws.lastFrame()).toMatchObject({ type: 'invite:send', payload: { tag: ann.tag } })
    ws.ack(socialFx.inviteSendAck)
    await settle()
    expect(within(friendRow('Ann')).getByRole('button', { name: 'Sent' })).toBeDisabled()
    act(() => vi.advanceTimersByTime(C.INVITE_COOLDOWN_MS - 2000))
    expect(within(friendRow('Ann')).getByRole('button', { name: 'Sent' })).toBeDisabled()
    act(() => vi.advanceTimersByTime(3000))
    expect(within(friendRow('Ann')).getByRole('button', { name: 'Invite Ann' })).toBeEnabled()
  })

  it('statuses update live in the sheet, and errors show a plain message', async () => {
    signIn()
    const { ws } = await open('/')
    await intoLobby(ws)
    fireEvent.click(screen.getByRole('button', { name: /Invite friends/ }))
    act(() => ws.receive({ type: 'friends:presence', data: { tag: socialFx.tags.Bob, status: 'online' } }))
    fireEvent.click(within(friendRow('Bob')).getByRole('button', { name: 'Invite Bob' }))
    ws.receive({ type: 'ack', id: ws.lastFrame().id, ok: false, error: socialFx.inviteSendErrors.TARGET_UNAVAILABLE })
    await settle()
    expect(screen.getByRole('alert')).toHaveTextContent("They can't be invited right now.")
    act(() => ws.receive({ type: 'friends:presence', data: { tag: socialFx.tags.Ann, status: 'busy' } }))
    expect(within(friendRow('Ann')).getByRole('button', { name: 'Unavailable' })).toBeDisabled()
  })

  it('without friends, the sheet says so and links to /friends', async () => {
    signIn()
    const { ws } = await open('/', socialFx.emptyOverview)
    await intoLobby(ws)
    fireEvent.click(screen.getByRole('button', { name: /Invite friends/ }))
    const sheet = screen.getByRole('dialog', { name: 'Invite friends' })
    expect(within(sheet).getByText('No friends yet. Add friends from the Friends page.')).toBeInTheDocument()
    expect(within(sheet).getByRole('link', { name: 'Go to Friends' })).toHaveAttribute('href', '/friends')
  })

  it('"{nickname} joined" when the invited friend takes a seat; nothing for others', async () => {
    signIn()
    const { ws } = await open('/')
    await intoLobby(ws)
    fireEvent.click(screen.getByRole('button', { name: /Invite friends/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Invite Ann' }))
    ws.ack(socialFx.inviteSendAck)
    await settle()
    const seat = (id: string, nickname: string, type: 'registered' | 'guest', avatar = ann.avatar) => ({
      ...ROOM.players[0],
      id,
      nickname,
      type,
      avatar,
    })
    act(() =>
      ws.receive({
        type: 'room:state',
        data: { ...ROOM, players: [...ROOM.players, seat('p_guest', 'Gus', 'guest', { style: 'x', seed: 'y' })] },
      }),
    )
    expect(screen.queryByText(/joined/)).not.toBeInTheDocument()
    act(() =>
      ws.receive({
        type: 'room:state',
        data: { ...ROOM, players: [...ROOM.players, seat('p_guest', 'Gus', 'guest', { style: 'x', seed: 'y' }), seat(socialFx.roomSeats.ann, 'Ann', 'registered')] },
      }),
    )
    expect(screen.getByText('Ann joined')).toBeInTheDocument()
  })
})

// ----- friends page and home ----------------------------------------------------------

describe('"Invite to play"', () => {
  it('is on every online friend row of /friends and Home, outside the ⋯ menu', async () => {
    signIn()
    await open('/friends')
    expect(within(friendRow('Ann')).getByRole('button', { name: 'Invite Ann to play' })).toBeVisible()
    expect(within(friendRow('Bob')).queryByRole('button', { name: /to play/ })).not.toBeInTheDocument()
    expect(within(friendRow('Cat')).queryByRole('button', { name: /to play/ })).not.toBeInTheDocument()
    act(() => go('/'))
    const section = screen.getByRole('region', { name: 'Friends online' })
    expect(within(section).getAllByText(/./, { selector: '.friend-row__name' }).map((e) => e.textContent)).toEqual(['Ann'])
    expect(within(section).getByRole('button', { name: 'Invite Ann to play' })).toBeVisible()
  })

  it('appears live when a friend comes online', async () => {
    signIn()
    const { ws } = await open('/')
    act(() => ws.receive({ type: 'friends:presence', data: { tag: socialFx.tags.Cat, status: 'online' } }))
    expect(screen.getByRole('button', { name: 'Invite Cat to play' })).toBeInTheDocument()
    act(() => ws.receive({ type: 'friends:presence', data: { tag: socialFx.tags.Ann, status: 'offline' } }))
    expect(screen.queryByRole('button', { name: 'Invite Ann to play' })).not.toBeInTheDocument()
  })

  it('outside a room: sets up a room, invites, then opens the lobby', async () => {
    signIn()
    const { ws } = await open('/friends')
    fireEvent.click(screen.getByRole('button', { name: 'Invite Ann to play' }))
    expect(within(friendRow('Ann')).getByRole('button', { name: 'Setting up your room…' })).toBeDisabled()
    expect(ws.lastFrame().type).toBe('room:create')
    ws.ack({ playerId: socialFx.roomSeats.sam, roomToken: 'tok', room: ROOM })
    await settle()
    expect(ws.lastFrame()).toMatchObject({ type: 'invite:send', payload: { tag: ann.tag } })
    ws.ack(socialFx.inviteSendAck)
    await settle()
    expect(screen.getByText('Room code')).toBeInTheDocument()
    expect(screen.getByText('Invite sent')).toBeInTheDocument()
  })

  it('does not set up a room if the friend is no longer online when tapped', async () => {
    signIn()
    const { ws } = await open('/friends')
    const button = screen.getByRole('button', { name: 'Invite Ann to play' })
    act(() => {
      ws.receive({ type: 'friends:presence', data: { tag: ann.tag, status: 'offline' } })
      fireEvent.click(button)
    })
    await settle()
    expect(ws.frames().map((f) => f.type)).not.toContain('room:create')
    expect(screen.getByRole('alert')).toHaveTextContent("Ann can't be invited right now.")
  })

  it('room set-up failure: a clear message, no invite', async () => {
    signIn()
    const { ws } = await open('/friends')
    fireEvent.click(screen.getByRole('button', { name: 'Invite Ann to play' }))
    ws.nack('RATE_LIMITED', 'Slow down.')
    await settle()
    expect(screen.getByRole('alert')).toHaveTextContent("We couldn't set up a room.")
    expect(ws.frames().map((f) => f.type)).not.toContain('invite:send')
    expect(screen.getByRole('button', { name: 'Invite Ann to play' })).toBeEnabled()
  })

  it('friend goes offline after the room is set up: lobby opens with a clear message', async () => {
    signIn()
    const { ws } = await open('/friends')
    fireEvent.click(screen.getByRole('button', { name: 'Invite Ann to play' }))
    ws.ack({ playerId: socialFx.roomSeats.sam, roomToken: 'tok', room: ROOM })
    await settle()
    ws.receive({ type: 'ack', id: ws.lastFrame().id, ok: false, error: socialFx.inviteSendErrors.TARGET_UNAVAILABLE })
    await settle()
    expect(screen.getByRole('alert')).toHaveTextContent("Your room is ready, but the invite didn't go through.")
    expect(screen.getByText('Room code')).toBeInTheDocument()
  })

  it('in a lobby: sends the invite right away and says "Invite sent"', async () => {
    signIn()
    const { ws } = await open('/')
    await intoLobby(ws)
    act(() => go('/friends'))
    await settle()
    const creates = ws.frames().filter((f) => f.type === 'room:create').length
    fireEvent.click(screen.getByRole('button', { name: 'Invite Ann to play' }))
    expect(ws.lastFrame()).toMatchObject({ type: 'invite:send', payload: { tag: ann.tag } })
    ws.ack(socialFx.inviteSendAck)
    await settle()
    expect(screen.getAllByText('Invite sent').length).toBeGreaterThan(0)
    expect(within(friendRow('Ann')).getByRole('button', { name: 'Invite sent' })).toBeDisabled()
    expect(ws.frames().filter((f) => f.type === 'room:create')).toHaveLength(creates)
  })

  it('in a running game: disabled and labelled "In a game"', async () => {
    signIn()
    const { ws } = await open('/')
    await intoLobby(ws)
    act(() => ws.receive({ type: 'room:state', data: { ...ROOM, status: 'playing', selectedGame: 'rps' } }))
    act(() => go('/friends'))
    await settle()
    expect(within(friendRow('Ann')).getByRole('button', { name: /In a game|you are in a game/ })).toBeDisabled()
  })
})

// ----- banners ------------------------------------------------------------------------

describe('invite banners', () => {
  const push = (ws: FakeWebSocket, data: unknown) => act(() => ws.receive({ type: 'invite:received', data }))
  const invite = socialFx.inviteReceived

  it('show sender, game and a countdown corrected for the server clock', async () => {
    signIn()
    vi.useFakeTimers({ toFake: ['Date', 'setInterval'] })
    const { ws } = await open('/')
    push(ws, invite) // serverNow is far from this clock: only the difference counts
    const banner = screen.getByRole('status', { name: 'Invite from Sam' })
    expect(banner).toHaveTextContent('Sam invited you to play Guess Race')
    expect(banner).toHaveTextContent('Expires in 2:00')
    expect(banner.querySelector('img, .chip__initial')).not.toBeNull()
    act(() => vi.advanceTimersByTime(61_000))
    expect(banner).toHaveTextContent('Expires in 0:59')
    act(() => vi.advanceTimersByTime(60_000))
    expect(screen.queryByRole('status', { name: 'Invite from Sam' })).not.toBeInTheDocument()
  })

  it('no game picked: no game name', async () => {
    signIn()
    const { ws } = await open('/')
    push(ws, { ...invite, gameId: null })
    expect(screen.getByRole('status', { name: 'Invite from Sam' })).toHaveTextContent(/invited you to play\s*Expires/)
  })

  it('Join accepts, then joins the room through the normal flow', async () => {
    signIn()
    const { ws } = await open('/friends')
    push(ws, invite)
    fireEvent.click(screen.getByRole('button', { name: 'Join Sam' }))
    expect(ws.lastFrame()).toMatchObject({ type: 'invite:accept', payload: { inviteId: invite.inviteId } })
    ws.ack(socialFx.inviteAcceptAck)
    await settle()
    expect(ws.lastFrame()).toMatchObject({ type: 'room:peek', payload: { code: socialFx.inviteAcceptAck.code } })
    expect(screen.queryByText(/invited you to play/)).not.toBeInTheDocument()
  })

  it.each([
    ['INVITE_EXPIRED', socialFx.inviteAcceptExpired, 'That invite has expired.'],
    ['INVITE_INVALID', socialFx.inviteAcceptErrors.INVITE_INVALID, 'That invite is no longer available.'],
  ])('%s on Join: a toast, and the banner goes', async (_code, error, message) => {
    signIn()
    const { ws } = await open('/')
    push(ws, invite)
    fireEvent.click(screen.getByRole('button', { name: 'Join Sam' }))
    ws.receive({ type: 'ack', id: ws.lastFrame().id, ok: false, error })
    await settle()
    expect(screen.getByRole('alert')).toHaveTextContent(message)
    expect(screen.queryByText(/invited you to play/)).not.toBeInTheDocument()
  })

  it('Decline sends invite:decline and removes the banner', async () => {
    signIn()
    const { ws } = await open('/')
    push(ws, invite)
    fireEvent.click(screen.getByRole('button', { name: 'Decline Sam' }))
    expect(ws.lastFrame()).toMatchObject({ type: 'invite:decline', payload: { inviteId: invite.inviteId } })
    expect(screen.queryByText(/invited you to play/)).not.toBeInTheDocument()
  })

  it('goes away on invite:expired and on invite:cleared (answered on another device)', async () => {
    signIn()
    const { ws } = await open('/')
    push(ws, { ...invite, inviteId: socialFx.inviteExpired.inviteId })
    push(ws, invite)
    expect(screen.getAllByText(/invited you to play/)).toHaveLength(2)
    act(() => ws.receive({ type: 'invite:expired', data: socialFx.inviteExpired }))
    expect(screen.getAllByText(/invited you to play/)).toHaveLength(1)
    act(() => ws.receive({ type: 'invite:cleared', data: socialFx.inviteCleared }))
    expect(screen.queryByText(/invited you to play/)).not.toBeInTheDocument()
  })

  it('stacks up to 3, ignores repeats, and is hidden inside a room', async () => {
    signIn()
    const { ws } = await open('/')
    for (const id of ['a', 'b', 'c', 'd']) push(ws, { ...invite, inviteId: `i_${id}` })
    push(ws, { ...invite, inviteId: 'i_d' })
    expect(screen.getAllByText(/invited you to play/)).toHaveLength(3)
    await intoLobby(ws)
    expect(screen.queryByText(/invited you to play/)).not.toBeInTheDocument()
  })
})

// ----- layout -------------------------------------------------------------------------

describe('layout', () => {
  it('320px: banners and rows wrap, buttons are tap height, nothing has a fixed width', () => {
    const css = readFileSync('src/styles/social.css', 'utf8')
    const rule = (name: string) => css.match(new RegExp(`\\.${name} \\{([^}]*)\\}`))![1]
    expect(rule('invite-banner')).toMatch(/flex-wrap: wrap/)
    expect(rule('invite-banner__text')).toMatch(/min-width: 0/)
    expect(rule('invite-banner__title,\\s*\\.invite-banner__time')).toMatch(/overflow-wrap: anywhere/)
    expect(rule('invite-friends')).toMatch(/min-height: var\(--tap\)/)
    expect(rule('invite-banners')).toMatch(/box-sizing: border-box/)
    for (const [, body] of css.matchAll(/\{([^}]*)\}/g)) expect(body).not.toMatch(/(^|\s)width: \d{3,}px/)
  })
})
