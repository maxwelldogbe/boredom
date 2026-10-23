import { describe, expect, it } from 'vitest'
import { C } from './constants'

describe('shared constants', () => {
  it('loads values from shared/constants.json', () => {
    expect(C.ROOM_CODE_LENGTH).toBe(4)
    expect(C.MAX_PLAYERS).toBe(10)
    expect(C.AVATAR_STYLES).toEqual(['adventurer-neutral', 'croodles-neutral', 'cutouts', 'voxel-art'])
    expect('EMOJI_PRESETS' in C).toBe(false)
    expect(C.PLAYER_COLORS).toHaveLength(10)
    expect(C.ROOM_CODE_ALPHABET).not.toMatch(/[IO]/)
  })
})
