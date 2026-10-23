import { afterEach, describe, expect, it, vi } from 'vitest'
import { C } from './constants'
import {
  createProfile,
  getProfile,
  importProfile,
  newId,
  nicknameError,
  PROFILE_KEY,
  resetProfile,
  saveProfile,
  toWireProfile,
} from './profileStore'
import { clearMemoryStorage } from './storage'

afterEach(() => {
  vi.restoreAllMocks()
  localStorage.clear()
  clearMemoryStorage()
})

const fields = { nickname: '  Sam  ', color: C.PLAYER_COLORS[2] }

describe('profileStore', () => {
  it('creates, saves and loads a guest profile', () => {
    const p = createProfile(fields)
    expect(p).toMatchObject({ nickname: 'Sam', type: 'guest', stats: { gamesPlayed: 0, wins: 0, byGame: {} } })
    expect(p.id).toMatch(/^[0-9a-f-]{36}$/)
    saveProfile(p)
    expect(getProfile()).toEqual(p)
    resetProfile()
    expect(getProfile()).toBeNull()
  })

  it('returns null for missing or corrupt storage', () => {
    expect(getProfile()).toBeNull()
    localStorage.setItem(PROFILE_KEY, '{oops')
    expect(getProfile()).toBeNull()
    localStorage.setItem(PROFILE_KEY, JSON.stringify({ id: 'x', nickname: 'Sam', color: '#000' }))
    expect(getProfile()).toBeNull()
  })

  it('still loads a profile saved before avatars existed, dropping its emoji', () => {
    const old = { ...createProfile(fields), emoji: '😀' }
    localStorage.setItem(PROFILE_KEY, JSON.stringify(old))
    const loaded = getProfile()
    expect(loaded?.id).toBe(old.id)
    expect(loaded).not.toHaveProperty('emoji')
  })

  it('keeps working when localStorage throws', () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('blocked')
    })
    const p = createProfile(fields)
    saveProfile(p)
    expect(getProfile()?.id).toBe(p.id)
  })

  it('validates nicknames with the shared rules', () => {
    expect(nicknameError('Sam')).toBeNull()
    expect(nicknameError('   ')).toMatch(/Enter/)
    expect(nicknameError('x'.repeat(C.NICKNAME_MAX + 1))).toMatch(/at most/)
    expect(nicknameError('<b>')).toMatch(/only/)
  })

  it('imports only valid profiles', () => {
    const p = createProfile(fields)
    expect(importProfile(JSON.stringify(p))).toEqual({ ok: true, profile: p })
    expect(importProfile('not json')).toMatchObject({ ok: false })
    expect(importProfile(JSON.stringify({ ...p, color: 'red' }))).toMatchObject({ ok: false })
  })

  it('never sends stats to the server', () => {
    expect(toWireProfile(createProfile(fields))).not.toHaveProperty('stats')
  })

  it('makes ids without crypto.randomUUID (plain-HTTP LAN)', () => {
    vi.spyOn(crypto, 'randomUUID').mockImplementation(() => {
      throw new Error('insecure context')
    })
    expect(newId()).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/)
  })
})
