/** Points as the server sends them (up to 2 decimals): 50 -> "50", 66.666 -> "66.67". */
export function formatPoints(n: number): string {
  return String(Math.round(n * 100) / 100)
}

/** "October 2026" from an ISO-8601 date. */
export function monthYear(iso: string): string {
  return new Intl.DateTimeFormat('en', { month: 'long', year: 'numeric', timeZone: 'UTC' }).format(new Date(iso))
}

/** "November 26, 2026" from epoch ms, in the viewer's time zone. */
export function longDate(ms: number): string {
  return new Intl.DateTimeFormat('en', { dateStyle: 'long' }).format(new Date(ms))
}

const RELATIVE_UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
  ['year', 365 * 24 * 3600],
  ['month', 30 * 24 * 3600],
  ['week', 7 * 24 * 3600],
  ['day', 24 * 3600],
  ['hour', 3600],
  ['minute', 60],
]

/** "2 hours ago", "yesterday", "just now" for an ISO-8601 time in the past. */
export function timeAgo(iso: string, now: number = Date.now()): string {
  const seconds = Math.round((new Date(iso).getTime() - now) / 1000)
  const format = new Intl.RelativeTimeFormat('en', { numeric: 'auto' })
  for (const [unit, size] of RELATIVE_UNITS) {
    if (Math.abs(seconds) >= size) return format.format(Math.round(seconds / size), unit)
  }
  return 'just now'
}

/** 0.4167 -> "42%"; null -> "—". */
export function formatRate(rate: number | null): string {
  return rate === null ? '—' : `${Math.round(rate * 100)}%`
}
