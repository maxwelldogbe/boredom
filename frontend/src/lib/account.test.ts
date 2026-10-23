import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { accountProfile, accountStats, fakeFetch } from '../test/fakeFetch'
import {
  AccountError,
  adoptSession,
  deleteAccount,
  fetchMe,
  forgetAccount,
  getAuthToken,
  login,
  passwordError,
  register,
  updateAccountProfile,
  usernameError,
} from './account'
import { createProfile, getProfile, saveProfile } from './profileStore'
import { clearMemoryStorage } from './storage'

let api: ReturnType<typeof fakeFetch>

beforeEach(() => {
  api = fakeFetch()
})
afterEach(() => {
  vi.unstubAllGlobals()
  localStorage.clear()
  clearMemoryStorage()
})

describe('account API client', () => {
  it('register sends the guest profile with its avatar and stats, then loads stats', async () => {
    const guest = {
      ...createProfile({ nickname: 'Sam', color: '#E74C3C' }),
      avatar: { style: 'cutouts', seed: 'saved1' },
      stats: { gamesPlayed: 2, wins: 1, byGame: { rps: { played: 2, wins: 1 } } },
    }
    api.reply(201, { token: 'jwt-1', profile: accountProfile })
    api.reply(200, { profile: accountProfile, stats: accountStats })
    const session = await register('sam_1', 'correct horse', guest)
    expect(api.calls[0]).toMatchObject({
      url: '/api/auth/register',
      method: 'POST',
      body: {
        username: 'sam_1',
        password: 'correct horse',
        profile: { nickname: 'Sam', color: '#E74C3C', avatar: guest.avatar, stats: guest.stats },
      },
    })
    expect(api.calls[0].body).not.toHaveProperty('profile.id')
    expect(api.calls[1]).toMatchObject({ url: '/api/auth/me', headers: { Authorization: 'Bearer jwt-1' } })
    expect(session).toEqual({ token: 'jwt-1', profile: accountProfile, stats: accountStats })
  })

  it('login, me, profile update and delete use the right method, path and token', async () => {
    api.reply(200, { token: 'jwt-2', profile: accountProfile, stats: accountStats })
    await login('sam_1', 'pw-12345678')
    api.reply(200, { profile: accountProfile, stats: accountStats })
    await fetchMe('jwt-2')
    api.reply(200, { profile: { ...accountProfile, nickname: 'Samwise' } })
    expect((await updateAccountProfile('jwt-2', { nickname: 'Samwise' })).nickname).toBe('Samwise')
    api.reply(200, { ok: true })
    await deleteAccount('jwt-2', 'pw-12345678')
    expect(api.calls.map((c) => `${c.method} ${c.url}`)).toEqual([
      'POST /api/auth/login',
      'GET /api/auth/me',
      'PATCH /api/auth/profile',
      'DELETE /api/auth/account',
    ])
    expect(api.calls[0].headers).not.toHaveProperty('Authorization')
    expect(api.calls.slice(1).every((c) => c.headers.Authorization === 'Bearer jwt-2')).toBe(true)
    expect(api.calls[3].body).toEqual({ password: 'pw-12345678' })
  })

  it('turns error responses into AccountError with code, friendly message and fields', async () => {
    api.reply(400, {
      error: { code: 'INVALID_INPUT', message: 'Some fields need fixing.', fields: { password: 'Too common.' } },
    })
    const err = await login('a', 'b').catch((e: unknown) => e)
    expect(err).toBeInstanceOf(AccountError)
    expect(err).toMatchObject({ code: 'INVALID_INPUT', fields: { password: 'Too common.' } })

    api.reply(401, { error: { code: 'INVALID_CREDENTIALS', message: 'Wrong username or password.' } })
    await expect(login('a', 'b')).rejects.toMatchObject({ code: 'INVALID_CREDENTIALS' })
    api.reply(429, { error: { code: 'RATE_LIMITED', message: 'x' } })
    await expect(login('a', 'b')).rejects.toMatchObject({
      code: 'RATE_LIMITED',
      message: 'Too many attempts. Wait a minute and try again.',
    })
    api.networkError()
    await expect(fetchMe('t')).rejects.toMatchObject({ code: 'NETWORK' })
    api.reply(500, null)
    await expect(fetchMe('t')).rejects.toMatchObject({ code: 'SERVER' })
  })

  it('validates usernames and passwords like the server', () => {
    expect(usernameError('sam_1')).toBeNull()
    expect(usernameError('ab')).not.toBeNull()
    expect(usernameError('sam smith')).not.toBeNull()
    expect(usernameError('x'.repeat(21))).not.toBeNull()
    expect(passwordError('1234567')).not.toBeNull()
    expect(passwordError('12345678')).toBeNull()
  })
})

describe('local profile', () => {
  it('adoptSession stores the token and the saved profile, keeping the device profile id', () => {
    const guest = createProfile({ nickname: 'Old', color: '#3498DB' })
    saveProfile(guest)
    const saved = adoptSession({ token: 'jwt-3', profile: accountProfile, stats: accountStats })
    expect(getAuthToken()).toBe('jwt-3')
    expect(saved).toMatchObject({
      id: guest.id,
      type: 'registered',
      username: 'sam_1',
      nickname: 'Sam',
      avatar: accountProfile.avatar,
      stats: accountStats,
    })
    expect(getProfile()).toEqual(saved)
  })

  it('adoptSession creates a profile on a new device', () => {
    expect(getProfile()).toBeNull()
    const saved = adoptSession({ token: 'jwt-4', profile: accountProfile, stats: accountStats })
    expect(saved.id).toBeTruthy()
    expect(getProfile()?.username).toBe('sam_1')
  })

  it('forgetAccount clears the token and returns to a guest with the same name', () => {
    adoptSession({ token: 'jwt-5', profile: accountProfile, stats: accountStats })
    const guest = forgetAccount()
    expect(getAuthToken()).toBeNull()
    expect(guest).toMatchObject({ type: 'guest', nickname: 'Sam', stats: { gamesPlayed: 0 } })
    expect(guest).not.toHaveProperty('username')
    expect(guest).not.toHaveProperty('avatar')
    expect(getProfile()).toEqual(guest)
  })

  it('a stored registered profile without a username loads as a guest', () => {
    localStorage.setItem(
      'partypack.profile',
      JSON.stringify({ ...createProfile({ nickname: 'Sam', color: '#E74C3C' }), type: 'registered' }),
    )
    expect(getProfile()?.type).toBe('guest')
  })
})
