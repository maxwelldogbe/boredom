/** Pure geometry for the penalty scene: SVG space (viewBox 390x844), the goal plane, gestures. */
import { C } from '../../lib/constants'
import type { GoalPoint, PenaltyOutcome } from '../../types/views'

export interface Pt {
  x: number
  y: number
}

/** A pointer sample in client pixels, `t` in ms. */
export interface Sample extends Pt {
  t: number
}

/** The affine part of an SVG screen CTM (SVG units to client pixels). */
export interface Matrix {
  a: number
  b: number
  c: number
  d: number
  e: number
  f: number
}

export const VIEW = { width: 390, height: 844 }
/** The goal mouth in SVG units. */
export const GOAL = { left: 55, right: 335, top: 150, bottom: 330 }
export const GOAL_W = GOAL.right - GOAL.left
export const GOAL_H = GOAL.bottom - GOAL.top
export const SPOT: Pt = { x: 195, y: 600 }
export const BALL_R = 17
/** How close to the ball (SVG units) the shooter's swipe must start. */
export const BALL_GRAB = 60
export const KEEPER_HOME: GoalPoint = { x: 0.5, y: 0.3 }
const SWIPE_WINDOW_MS = 120
/** Shorter stretches are ignored: a jitter between two close samples is not a flick. */
const SWIPE_MIN_DT_MS = 30

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v))

export function goalToSvg(p: GoalPoint): Pt {
  return { x: GOAL.left + p.x * GOAL_W, y: GOAL.bottom - p.y * GOAL_H }
}

export function svgToGoal(p: Pt): GoalPoint {
  return { x: (p.x - GOAL.left) / GOAL_W, y: (GOAL.bottom - p.y) / GOAL_H }
}

/** A client point in SVG units, inverting the screen CTM (works under "slice"). No CTM: identity. */
export function clientToSvg(x: number, y: number, m: Matrix | null): Pt {
  if (!m) return { x, y }
  const det = m.a * m.d - m.b * m.c
  const dx = x - m.e
  const dy = y - m.f
  return { x: (m.d * dx - m.c * dy) / det, y: (m.a * dy - m.b * dx) / det }
}

export function nearBall(p: Pt): boolean {
  return Math.hypot(p.x - SPOT.x, p.y - SPOT.y) <= BALL_GRAB
}

/** Where the shooter's release point aims, clamped to the range the server accepts. */
export function aimFromRelease(p: Pt): GoalPoint {
  const g = svgToGoal(p)
  return { x: clamp(g.x, -0.5, 1.5), y: clamp(g.y, -0.5, 1.5) }
}

/** The target ring is shown only over a sensible area: above the ball, around the goal. */
export function showTarget(p: Pt): boolean {
  const g = svgToGoal(p)
  return p.y < SPOT.y - BALL_GRAB && g.x >= -0.5 && g.x <= 1.5 && g.y <= 1.5
}

export function isShortSwipe(start: Pt, end: Pt): boolean {
  return Math.hypot(end.x - start.x, end.y - start.y) < C.PENALTY_SWIPE_MIN_PX
}

/**
 * Peak swipe speed in px/ms: the fastest ~120 ms stretch of the swipe, so pausing on the
 * target before lifting the finger keeps the flick's power.
 */
export function swipeSpeed(samples: Sample[]): number {
  let peak = 0
  let start = 0
  for (let j = 1; j < samples.length; j++) {
    while (start + 1 < j && samples[j].t - samples[start + 1].t >= SWIPE_WINDOW_MS) start++
    const a = samples[start]
    const b = samples[j]
    const dt = b.t - a.t
    if (dt >= SWIPE_MIN_DT_MS) peak = Math.max(peak, Math.hypot(b.x - a.x, b.y - a.y) / dt)
  }
  return peak
}

/** Linear from PENALTY_SPEED_MIN (0) to PENALTY_SPEED_MAX (1), clamped. */
export function powerFromSpeed(speed: number): number {
  const lo = C.PENALTY_SPEED_MIN_PX_PER_MS
  const hi = C.PENALTY_SPEED_MAX_PX_PER_MS
  return clamp((speed - lo) / (hi - lo), 0, 1)
}

/** The keeper's dive point: where the keeper stands plus the swipe (SVG units) in goal-plane units. */
export function diveFromSwipe(spot: GoalPoint, dx: number, dy: number): GoalPoint {
  return { x: clamp(spot.x + dx / GOAL_W, -0.1, 1.1), y: clamp(spot.y - dy / GOAL_H, -0.1, 1.1) }
}

/** Where the patrolling keeper is at server time `now` (as the server computes it). */
export function keeperAt(path: (GoalPoint & { at: number })[] | null, now: number): GoalPoint {
  if (!path || path.length === 0) return KEEPER_HOME
  for (let i = 1; i < path.length; i++) {
    const a = path[i - 1]
    const b = path[i]
    if (now < b.at) {
      const k = Math.max(0, (now - a.at) / (b.at - a.at))
      return { x: a.x + (b.x - a.x) * k, y: a.y + (b.y - a.y) * k }
    }
  }
  const last = path[path.length - 1]
  return { x: last.x, y: last.y }
}

/** Where the ball ends: beside, above or against the frame, short (fizzled), in the hands after a dive, or on the body. */
export function ballEnd(to: GoalPoint, power: number, outcome: PenaltyOutcome | null, dive: GoalPoint | null): Pt {
  if (outcome === 'fizzled' || (outcome === null && power < C.PENALTY_POWER_FIZZLE)) {
    const aim = goalToSvg(to)
    return { x: SPOT.x + (aim.x - SPOT.x) * 0.4, y: SPOT.y + (aim.y - SPOT.y) * 0.4 }
  }
  if (outcome === 'saved') return goalToSvg(dive ?? to)
  const p = goalToSvg(to)
  return { x: clamp(p.x, 8, VIEW.width - 8), y: Math.max(40, p.y) }
}

/** The ball at flight progress `t` (0..1): a curved path that shrinks with distance. */
export function ballAt(end: Pt, t: number, fizzled: boolean): Pt & { r: number } {
  const k = clamp(t, 0, 1)
  const cx = (SPOT.x + end.x) / 2
  const cy = Math.min(SPOT.y, end.y) - (fizzled ? 10 : 70)
  const u = 1 - k
  return {
    x: u * u * SPOT.x + 2 * u * k * cx + k * k * end.x,
    y: u * u * SPOT.y + 2 * u * k * cy + k * k * end.y,
    r: BALL_R * (1 - (fizzled ? 0.25 : 0.55) * k),
  }
}

/**
 * The keeper standing at `spot`, or diving from it: the hands' offset from the drawn home
 * position and a lean (degrees, clockwise) around the hands, as the server poses its hitbox.
 */
export function keeperPose(spot: GoalPoint, dive: GoalPoint | null): { dx: number; dy: number; angle: number } {
  const home = goalToSvg(KEEPER_HOME)
  const p = goalToSvg(dive ?? spot)
  return { dx: p.x - home.x, dy: p.y - home.y, angle: dive ? clamp((dive.x - spot.x) * 160, -80, 80) : 0 }
}
