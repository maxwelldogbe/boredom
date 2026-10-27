import { act, fireEvent, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { AppRoutes } from '../App'
import { communityUrl, WHATSAPP_CHANNEL_URL } from '../config/community'
import { adoptSession } from '../lib/account'
import { clearMemoryStorage } from '../lib/storage'
import { fakeFetch } from '../test/fakeFetch'
import { FakeWebSocket } from '../test/fakeWebSocket'
import { profileFx, roomFx } from '../test/fixtures'
import { renderWithRoom, saveTestProfile } from '../test/render'
import type { RoomPublic } from '../types/protocol'

// Lets a test pretend the configured link is something else.
const override = vi.hoisted(() => ({ url: undefined as string | undefined }))
vi.mock('../config/community', async (load) => {
  const real = await load<typeof import('../config/community')>()
  return { ...real, communityUrl: (url?: string) => real.communityUrl(override.url ?? url) }
})

const FINISHED = roomFx.roomFinished
const ME = FINISHED.hostId
const LOBBY: RoomPublic = { ...FINISHED, status: 'lobby' }
const NAME = 'Join our WhatsApp community (opens in a new tab)'

beforeEach(() => {
  FakeWebSocket.reset()
  fakeFetch()
})
afterEach(() => {
  override.url = undefined
  vi.unstubAllGlobals()
  localStorage.clear()
  clearMemoryStorage()
})

async function settle() {
  await act(async () => {
    for (let i = 0; i < 4; i++) await Promise.resolve()
  })
}

async function app(route = '/') {
  const view = renderWithRoom(<AppRoutes />, { route })
  await settle()
  return view
}

async function intoRoom() {
  const { ws } = await app('/')
  fireEvent.click(screen.getByRole('button', { name: 'Create room' }))
  await settle()
  ws.ack({ playerId: ME, roomToken: 'tok', room: LOBBY }, ws.frames().find((f) => f.type === 'room:create')!.id)
  await settle()
  return ws
}

function expectLink(link: HTMLElement) {
  expect(link).toHaveAttribute('href', WHATSAPP_CHANNEL_URL)
  expect(link).toHaveAttribute('target', '_blank')
  expect(link).toHaveAttribute('rel', 'noopener noreferrer')
  expect(link).toHaveTextContent('Join our WhatsApp community')
  expect(link.querySelector('svg[aria-hidden="true"]')).not.toBeNull()
}

const asGuest = () => saveTestProfile()
const asRegistered = () => adoptSession({ token: 'jwt-1', profile: profileFx.me.profile, stats: profileFx.me.stats })

describe.each([
  ['guests', asGuest],
  ['registered players', asRegistered],
])('community link for %s', (_who, signIn) => {
  it('Home: below the main actions, with the short line', async () => {
    signIn()
    await app('/')
    const link = screen.getByRole('link', { name: NAME })
    expectLink(link)
    const actions = screen.getByRole('button', { name: 'Create room' }).closest('.home__actions')!
    expect(actions.compareDocumentPosition(link) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(screen.getByText('Share your experience and meet other players.')).toBeInTheDocument()
  })

  it('top-bar menu in the lobby and during a game', async () => {
    signIn()
    const ws = await intoRoom()
    fireEvent.click(screen.getByRole('button', { name: 'Menu' }))
    expectLink(within(document.querySelector<HTMLElement>('.topbar__menu-panel')!).getByRole('link', { name: NAME }))
    fireEvent.click(screen.getByRole('button', { name: 'Menu' }))
    act(() => ws.receive({ type: 'room:state', data: { ...FINISHED, status: 'playing', selectedGame: 'rps' } }))
    fireEvent.click(screen.getByRole('button', { name: 'Menu' }))
    expectLink(within(document.querySelector<HTMLElement>('.topbar__menu-panel')!).getByRole('link', { name: NAME }))
  })

  it('final results: small and secondary', async () => {
    signIn()
    const ws = await intoRoom()
    act(() => ws.receive({ type: 'room:state', data: FINISHED }))
    const link = within(document.querySelector<HTMLElement>('.results')!).getByRole('link', { name: NAME })
    expectLink(link)
    expect(link).toHaveClass('btn--secondary', 'community--small')
  })

  it('/about, with the line about WhatsApp in what we record', async () => {
    signIn()
    await app('/about')
    expectLink(screen.getByRole('link', { name: NAME }))
    expect(screen.getByText('Share your experience and meet other players.')).toBeInTheDocument()
    const record = screen.getByRole('region', { name: 'What we record' })
    expect(record).toHaveTextContent('Links to our community open WhatsApp, which has its own privacy policy.')
  })
})

describe('community link config', () => {
  it.each(['', '   ', 'http://whatsapp.com/channel/x', 'https://PLACEHOLDER', 'whatsapp.com/channel/x', 'https://'])(
    'hides for %j',
    (url) => {
      expect(communityUrl(url)).toBeNull()
    },
  )

  it('accepts the configured https link', () => {
    expect(communityUrl()).toBe(WHATSAPP_CHANNEL_URL)
  })

  it('an unusable link hides every button and the About line, without errors', async () => {
    override.url = 'https://your-channel-link-placeholder'
    const errors = vi.spyOn(console, 'error')
    asGuest()
    const view = await app('/')
    expect(screen.queryByRole('link', { name: NAME })).toBeNull()
    expect(screen.queryByText('Share your experience and meet other players.')).toBeNull()
    view.unmount()
    await app('/about')
    expect(screen.queryByRole('link', { name: NAME })).toBeNull()
    expect(screen.queryByText(/open WhatsApp/)).toBeNull()
    expect(errors).not.toHaveBeenCalled()
  })

  it('profile text is unchanged (the WhatsApp line is only on /about)', async () => {
    asGuest()
    await app('/profile')
    expect(screen.getByRole('region', { name: 'What we save' })).not.toHaveTextContent(/WhatsApp/)
  })
})
