import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { AppRoutes } from '../App'
import { AccountSync, LOGIN_EXPIRED_MESSAGE } from '../components/AccountSync'
import { PlayerChip } from '../components/PlayerChip'
import { ToastHost } from '../components/ToastHost'
import { adoptSession, getAuthToken } from '../lib/account'
import { getProfile, saveProfile } from '../lib/profileStore'
import { clearMemoryStorage } from '../lib/storage'
import { accountProfile, accountStats, fakeFetch } from '../test/fakeFetch'
import { FakeWebSocket } from '../test/fakeWebSocket'
import { renderWithRoom, saveTestProfile } from '../test/render'

let api: ReturnType<typeof fakeFetch>

beforeEach(() => {
  FakeWebSocket.reset()
  api = fakeFetch()
})
afterEach(() => {
  vi.unstubAllGlobals()
  localStorage.clear()
  clearMemoryStorage()
})

function app(route: string) {
  return renderWithRoom(
    <>
      <AppRoutes />
      <ToastHost />
    </>,
    { route },
  )
}

function signIn() {
  adoptSession({ token: 'jwt-1', profile: accountProfile, stats: accountStats })
}

function type(label: string, value: string, scope: HTMLElement = document.body) {
  fireEvent.change(within(scope).getByLabelText(label), { target: { value } })
}

describe('guest profile page: save your profile', () => {
  it('creates an account from the guest profile (keeping its avatar)', async () => {
    const guest = saveTestProfile('Sam')
    saveProfile({ ...guest, avatar: { style: 'cutouts', seed: 'saved1' } })
    app('/profile')
    const card = screen.getByRole('region', { name: 'Save your profile' })
    expect(within(card).getByRole('tab', { name: 'Create account' })).toHaveAttribute('aria-selected', 'true')

    type('Username', 'sam_1', card)
    type('Password', 'short', card)
    fireEvent.click(within(card).getByRole('button', { name: 'Create account' }))
    expect(within(card).getByText('Use at least 8 characters.')).toBeInTheDocument()
    expect(api.calls).toHaveLength(0)

    api.reply(201, { token: 'jwt-1', profile: accountProfile })
    api.reply(200, { profile: accountProfile, stats: accountStats })
    api.reply(200, { profile: accountProfile, stats: accountStats }) // the account page refresh
    type('Password', 'correct horse', card)
    fireEvent.click(within(card).getByRole('button', { name: 'Create account' }))

    expect(await screen.findByRole('heading', { level: 1, name: 'Sam' })).toBeInTheDocument()
    expect(document.body.textContent).not.toContain('sam_1') // the login username is never shown
    expect(api.calls[0].body).toMatchObject({ profile: { avatar: { style: 'cutouts', seed: 'saved1' } } })
    expect(screen.getByText('Account created. Your profile is saved.')).toBeInTheDocument()
    expect(getAuthToken()).toBe('jwt-1')
    expect(getProfile()).toMatchObject({ type: 'registered', username: 'sam_1', id: guest.id })
  })

  it('shows a taken username and server password errors next to the fields', async () => {
    saveTestProfile('Sam')
    app('/profile')
    const card = screen.getByRole('region', { name: 'Save your profile' })
    api.reply(409, {
      error: { code: 'USERNAME_TAKEN', message: 'That username is taken.', fields: { username: 'Taken.' } },
    })
    type('Username', 'sam_1', card)
    type('Password', 'correct horse', card)
    fireEvent.click(within(card).getByRole('button', { name: 'Create account' }))
    expect(await within(card).findByText('That username is taken.')).toBeInTheDocument()

    api.reply(400, {
      error: { code: 'INVALID_INPUT', message: 'Some fields need fixing.', fields: { password: 'This password is too common.' } },
    })
    type('Username', 'sam_2', card)
    fireEvent.click(within(card).getByRole('button', { name: 'Create account' }))
    expect(await within(card).findByText('This password is too common.')).toBeInTheDocument()
    expect(getAuthToken()).toBeNull()
  })

  it('logs in to an existing account from the second tab', async () => {
    saveTestProfile('Guesty')
    app('/profile')
    const card = screen.getByRole('region', { name: 'Save your profile' })
    fireEvent.click(within(card).getByRole('tab', { name: 'Log in' }))
    api.reply(401, { error: { code: 'INVALID_CREDENTIALS', message: 'Wrong username or password.' } })
    type('Username', 'sam_1', card)
    type('Password', 'wrong-password', card)
    fireEvent.click(within(card).getByRole('button', { name: 'Log in' }))
    expect(await within(card).findByRole('alert')).toHaveTextContent('Wrong username or password.')

    api.reply(200, { token: 'jwt-2', profile: accountProfile, stats: accountStats })
    api.reply(200, { profile: accountProfile, stats: accountStats })
    type('Password', 'correct horse', card)
    fireEvent.click(within(card).getByRole('button', { name: 'Log in' }))
    expect(await screen.findByRole('heading', { level: 1, name: 'Sam' })).toBeInTheDocument()
    expect(document.body.textContent).not.toContain('sam_1') // the login username is never shown
    expect(screen.getByText('Welcome back, Sam!')).toBeInTheDocument()
    expect(getProfile()?.nickname).toBe('Sam') // the saved nickname replaces the guest one
  })
})

describe('registered profile page', () => {
  it('refreshes from the server, shows stats and saves changes to the account', async () => {
    signIn()
    api.reply(200, { profile: accountProfile, stats: { ...accountStats, gamesPlayed: 4, wins: 2 } })
    api.route('/api/me/stats', 200, {
      totals: { played: 4, wins: 2, losses: 2, winRate: null },
      favoriteGame: 'rps',
      perGame: [{ gameId: 'rps', played: 4, wins: 2, losses: 2, winRate: null }],
      minGamesForRate: 5,
    })
    app('/profile')
    expect(screen.getByRole('heading', { level: 1, name: 'Sam' })).toBeInTheDocument()
    const byGame = await screen.findByRole('region', { name: 'By game' })
    expect(within(byGame).getByText('Rock-Paper-Scissors')).toBeInTheDocument()
    expect(document.body.textContent).not.toContain('sam_1')
    expect(screen.getByRole('group', { name: 'Avatar' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Export profile' })).not.toBeInTheDocument()

    api.reply(200, { profile: { ...accountProfile, nickname: 'Samwise' } })
    type('Nickname', 'Samwise')
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))
    expect(await screen.findByText('Profile saved.')).toBeInTheDocument()
    expect(api.calls[1]).toMatchObject({
      method: 'PATCH',
      url: '/api/auth/profile',
      body: { nickname: 'Samwise', color: '#E74C3C' },
      headers: { Authorization: 'Bearer jwt-1' },
    })
    expect(getProfile()?.nickname).toBe('Samwise')
  })

  it('logs out back to a guest on this device', async () => {
    signIn()
    api.reply(200, { profile: accountProfile, stats: accountStats })
    app('/profile')
    await waitFor(() => expect(api.calls).toHaveLength(1))
    fireEvent.click(screen.getByRole('button', { name: 'Log out' }))
    expect(getAuthToken()).toBeNull()
    expect(getProfile()).toMatchObject({ type: 'guest', nickname: 'Sam' })
    expect(screen.getByRole('region', { name: 'Save your profile' })).toBeInTheDocument()
    expect(screen.getByText("Logged out. You're playing as a guest on this device.")).toBeInTheDocument()
  })

  it('deletes the account only with the right password', async () => {
    signIn()
    api.reply(200, { profile: accountProfile, stats: accountStats })
    app('/profile')
    await waitFor(() => expect(api.calls).toHaveLength(1))
    fireEvent.click(screen.getByRole('button', { name: 'Delete account' }))
    const dialog = screen.getByRole('dialog')
    api.reply(401, { error: { code: 'INVALID_CREDENTIALS', message: 'Wrong password.' } })
    type('Password', 'nope-nope', dialog)
    fireEvent.click(within(dialog).getByRole('button', { name: 'Delete account' }))
    expect(await within(dialog).findByText('Wrong password.')).toBeInTheDocument()
    expect(getAuthToken()).toBe('jwt-1')

    api.reply(200, { ok: true })
    type('Password', 'correct horse', dialog)
    fireEvent.click(within(dialog).getByRole('button', { name: 'Delete account' }))
    expect(await screen.findByText('Your account was deleted.')).toBeInTheDocument()
    expect(api.calls[2]).toMatchObject({ method: 'DELETE', body: { password: 'correct horse' } })
    expect(getAuthToken()).toBeNull()
    expect(getProfile()?.type).toBe('guest')
  })

  it('an expired token on the profile page falls back to a guest', async () => {
    signIn()
    api.reply(401, { error: { code: 'UNAUTHORIZED', message: 'Please log in again.' } })
    app('/profile')
    expect(await screen.findByRole('region', { name: 'Save your profile' })).toBeInTheDocument()
    expect(getAuthToken()).toBeNull()
  })
})

describe('new device and home', () => {
  it('logs in from setup and continues to where the player was going', async () => {
    app('/setup?next=%2Fjoin%2FABCD')
    fireEvent.click(screen.getByRole('button', { name: 'I already have an account' }))
    expect(screen.getByRole('heading', { name: 'Log in' })).toBeInTheDocument()
    expect(screen.queryByRole('tab')).not.toBeInTheDocument()
    api.reply(200, { token: 'jwt-9', profile: accountProfile, stats: accountStats })
    type('Username', 'sam_1')
    type('Password', 'correct horse')
    fireEvent.click(screen.getByRole('button', { name: 'Log in' }))
    expect(await screen.findByText('Joining room ABCD')).toBeInTheDocument()
    expect(getProfile()).toMatchObject({ type: 'registered', nickname: 'Sam' })
  })

  it('home links to log in or to saving the profile', () => {
    const { unmount } = app('/')
    expect(screen.getByRole('link', { name: 'Have an account? Log in' })).toHaveAttribute(
      'href',
      '/setup?mode=login',
    )
    unmount()
    saveTestProfile('Sam')
    app('/')
    expect(screen.getByRole('link', { name: 'Save your profile with a free account' })).toHaveAttribute(
      'href',
      '/profile',
    )
  })

  it('home shows no account link once logged in', () => {
    signIn()
    app('/')
    expect(screen.queryByText(/free account|Log in/)).not.toBeInTheDocument()
  })
})

describe('AccountSync', () => {
  it('forgets an expired login on start-up and says so', async () => {
    signIn()
    api.reply(401, { error: { code: 'UNAUTHORIZED', message: 'x' } })
    renderWithRoom(
      <>
        <AccountSync />
        <ToastHost />
      </>,
    )
    expect(await screen.findByRole('alert')).toHaveTextContent(LOGIN_EXPIRED_MESSAGE)
    expect(getAuthToken()).toBeNull()
    expect(getProfile()?.type).toBe('guest')
  })

  it('keeps the login when the server cannot be reached', async () => {
    signIn()
    api.networkError()
    renderWithRoom(<AccountSync />)
    await act(async () => {
      await Promise.resolve()
    })
    expect(getAuthToken()).toBe('jwt-1')
  })

  it('does nothing for guests', () => {
    saveTestProfile('Sam')
    renderWithRoom(<AccountSync />)
    expect(api.calls).toHaveLength(0)
  })
})

describe('PlayerChip', () => {
  it('marks registered players with a saved-profile badge', () => {
    render(<PlayerChip player={{ nickname: 'Sam', color: '#E74C3C', type: 'registered' }} />)
    expect(screen.getByText('saved profile')).toBeInTheDocument()
  })

  it('shows no badge for guests', () => {
    render(<PlayerChip player={{ nickname: 'Ann', color: '#E74C3C', type: 'guest' }} />)
    expect(screen.queryByText('saved profile')).not.toBeInTheDocument()
  })
})
