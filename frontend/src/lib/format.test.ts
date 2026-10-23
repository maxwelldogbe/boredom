import { describe, expect, it } from 'vitest'
import { formatPoints } from './format'

describe('formatPoints', () => {
  it('drops trailing zeros and keeps at most 2 decimals', () => {
    expect(formatPoints(100)).toBe('100')
    expect(formatPoints(66.67)).toBe('66.67')
    expect(formatPoints(10 / 3)).toBe('3.33')
    expect(formatPoints(0)).toBe('0')
  })
})
