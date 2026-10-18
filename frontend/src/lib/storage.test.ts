import { afterEach, describe, expect, it, vi } from 'vitest'
import { clearRoomToken, getRoomToken, setRoomToken } from './roomTokens'
import { clearMemoryStorage, readItem, removeItem, writeItem } from './storage'

afterEach(() => {
  vi.restoreAllMocks()
  localStorage.clear()
  clearMemoryStorage()
})

describe('storage', () => {
  it('round-trips through localStorage', () => {
    writeItem('k', 'v')
    expect(localStorage.getItem('k')).toBe('v')
    expect(readItem('k')).toBe('v')
    removeItem('k')
    expect(readItem('k')).toBeNull()
  })

  it('falls back to memory when localStorage throws', () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('quota')
    })
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked')
    })
    writeItem('k', 'v')
    expect(readItem('k')).toBe('v')
  })
})

describe('roomTokens', () => {
  it('stores tokens per room code, case-insensitively', () => {
    setRoomToken('abcd', 't1')
    setRoomToken('EFGH', 't2')
    expect(getRoomToken('ABCD')).toBe('t1')
    expect(getRoomToken('efgh')).toBe('t2')
    clearRoomToken('ABCD')
    expect(getRoomToken('ABCD')).toBeNull()
    expect(getRoomToken('EFGH')).toBe('t2')
  })

  it('survives a corrupt stored value', () => {
    localStorage.setItem('partypack.roomTokens', '{not json')
    expect(getRoomToken('ABCD')).toBeNull()
    setRoomToken('ABCD', 't')
    expect(getRoomToken('ABCD')).toBe('t')
  })
})
