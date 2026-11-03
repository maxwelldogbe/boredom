import { describe, expect, it } from 'vitest'
import { C } from '../../lib/constants'
import {
  aimFromRelease,
  clientToSvg,
  diveFromSwipe,
  goalToSvg,
  isShortSwipe,
  keeperAt,
  keeperPose,
  nearBall,
  powerFromSpeed,
  SPOT,
  swipeSpeed,
} from './geometry'

describe('penalty gestures', () => {
  it('maps a release point to the goal plane, also under a scaled viewBox', () => {
    expect(aimFromRelease({ x: 55, y: 330 })).toEqual({ x: 0, y: 0 })
    expect(aimFromRelease({ x: 335, y: 150 })).toEqual({ x: 1, y: 1 })
    expect(aimFromRelease({ x: -500, y: 900 })).toEqual({ x: -0.5, y: -0.5 })
    // "slice" at half scale, the viewBox shifted 10px right and 20px up on screen
    const m = { a: 0.5, b: 0, c: 0, d: 0.5, e: 10, f: -20 }
    const svg = clientToSvg(10 + 0.5 * 195, -20 + 0.5 * 240, m)
    expect(svg).toEqual({ x: 195, y: 240 })
    expect(aimFromRelease(svg)).toEqual({ x: 0.5, y: 0.5 })
    expect(goalToSvg({ x: 0.5, y: 0.5 })).toEqual(svg)
  })

  it('keeps the flick power when the finger pauses on the target before lifting', () => {
    const flickThenPause = [
      { x: 0, y: 0, t: 0 },
      { x: 0, y: -300, t: 100 },
      { x: 0, y: -300, t: 400 }, // still on the target, then released
    ]
    expect(swipeSpeed(flickThenPause)).toBe(3)
    expect(powerFromSpeed(swipeSpeed(flickThenPause))).toBe(1)
    expect(swipeSpeed([{ x: 0, y: 0, t: 0 }, { x: 0, y: -50, t: 5 }])).toBe(0) // jitter, not a flick
  })

  it('maps the fastest ~120 ms of the swipe to power', () => {
    const { PENALTY_SPEED_MIN_PX_PER_MS: lo, PENALTY_SPEED_MAX_PX_PER_MS: hi } = C
    expect(powerFromSpeed(lo / 2)).toBe(0)
    expect(powerFromSpeed((lo + hi) / 2)).toBeCloseTo(0.5)
    expect(powerFromSpeed(hi * 2)).toBe(1)
    const samples = [
      { x: 0, y: 0, t: 0 },
      { x: 0, y: 0, t: 300 }, // a slow start is not counted
      { x: 0, y: -100, t: 400 },
      { x: 0, y: -150, t: 420 },
    ]
    expect(swipeSpeed(samples)).toBeCloseTo(150 / 120)
    expect(swipeSpeed(samples.slice(0, 1))).toBe(0)
  })

  it('turns a keeper swipe into a dive point from where the keeper stands, a longer swipe reaching further', () => {
    const home = { x: 0.5, y: 0.3 }
    expect(diveFromSwipe(home, 0, 0)).toEqual(home)
    expect(diveFromSwipe(home, 140, -90)).toEqual({ x: 1, y: 0.8 })
    expect(diveFromSwipe({ x: 0.25, y: 0.3 }, 140, 0)).toEqual({ x: 0.75, y: 0.3 })
    expect(diveFromSwipe(home, -70, 0).x).toBeGreaterThan(diveFromSwipe(home, -140, 0).x)
    expect(diveFromSwipe(home, 1000, 1000)).toEqual({ x: 1.1, y: -0.1 })
  })

  it('follows the keeper patrol like the server, and poses the dive from the keeper spot', () => {
    const path = [
      { at: 1000, x: 0.5, y: 0.3 },
      { at: 1350, x: 0.5, y: 0.3 },
      { at: 1850, x: 0.7, y: 0.34 },
    ]
    expect(keeperAt(null, 5000)).toEqual({ x: 0.5, y: 0.3 })
    expect(keeperAt(path, 1200)).toEqual({ x: 0.5, y: 0.3 })
    const mid = keeperAt(path, 1600)
    expect(mid.x).toBeCloseTo(0.6)
    expect(mid.y).toBeCloseTo(0.32)
    expect(keeperAt(path, 9000)).toEqual({ x: 0.7, y: 0.34 })
    expect(keeperPose({ x: 0.75, y: 0.3 }, null)).toEqual({ dx: 70, dy: 0, angle: 0 })
    const pose = keeperPose({ x: 0.75, y: 0.3 }, { x: 0.25, y: 0.3 })
    expect(pose).toEqual({ dx: -70, dy: 0, angle: -80 })
  })

  it('rejects short swipes and swipes that do not start at the ball', () => {
    expect(isShortSwipe({ x: 0, y: 0 }, { x: 0, y: C.PENALTY_SWIPE_MIN_PX - 1 })).toBe(true)
    expect(isShortSwipe({ x: 0, y: 0 }, { x: 0, y: C.PENALTY_SWIPE_MIN_PX })).toBe(false)
    expect(nearBall({ x: SPOT.x + 40, y: SPOT.y - 30 })).toBe(true)
    expect(nearBall({ x: SPOT.x, y: SPOT.y - 100 })).toBe(false)
  })
})
