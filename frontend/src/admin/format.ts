import type { ActorRef } from './api'

/** Display helpers for the dashboard. Missing values show as an em dash. */
export const DASH = '—'

export function fmtInt(n: number | null | undefined): string {
  return n === null || n === undefined ? DASH : n.toLocaleString('en')
}

export function fmtNum(n: number | null | undefined, digits = 1): string {
  return n === null || n === undefined ? DASH : n.toFixed(digits)
}

export function fmtPct(ratio: number | null | undefined): string {
  return ratio === null || ratio === undefined ? DASH : `${Math.round(ratio * 100)}%`
}

/** 78 -> "1m 18s", 3725 -> "1h 02m". */
export function fmtDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return DASH
  const total = Math.round(seconds)
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = total % 60
  if (h) return `${h}h ${String(m).padStart(2, '0')}m`
  return m ? `${m}m ${String(s).padStart(2, '0')}s` : `${s}s`
}

/** An ISO timestamp in the server's display time zone, e.g. "23 Oct 2026, 14:05". */
export function fmtDateTime(iso: string | null | undefined, timeZone?: string): string {
  if (!iso) return DASH
  return new Intl.DateTimeFormat('en-GB', {
    timeZone,
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(iso))
}

export function fmtDate(iso: string | null | undefined, timeZone?: string): string {
  if (!iso) return DASH
  return new Intl.DateTimeFormat('en-GB', { timeZone, day: 'numeric', month: 'short', year: 'numeric' }).format(
    new Date(iso),
  )
}

/** A calendar day "2026-10-23" (already in the display zone) as "Fri 23 Oct". */
export function fmtDay(day: string, weekday = true): string {
  const [y, m, d] = day.split('-').map(Number)
  return new Intl.DateTimeFormat('en-GB', {
    ...(weekday ? { weekday: 'short' } : {}),
    day: 'numeric',
    month: 'short',
  }).format(new Date(y, m - 1, d))
}

/** The smallest "nice" axis top (1, 2, 5 x 10^k) at or above `peak`. */
export function niceMax(peak: number): number {
  if (peak <= 0) return 1
  const power = 10 ** Math.floor(Math.log10(peak))
  for (const step of [1, 2, 5, 10]) if (step * power >= peak) return step * power
  return 10 * power
}

/** The dashboard page of a registered account or a guest. */
export function actorPath(actor: ActorRef): string {
  return actor.kind === 'registered' ? `/admin/users/u/${actor.userId}` : `/admin/users/g/${actor.guestKey}`
}
