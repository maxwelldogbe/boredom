/** Money display for the console. The server sends integer pesewas; this only formats them. */
import { C } from '../../lib/constants'
import { formatMoney, parseMoney } from '../../lib/nemesis'

export function fmtMoney(amount: number | null | undefined): string {
  return amount === null || amount === undefined ? '—' : formatMoney(amount, C.CURRENCY, C.MINOR_UNIT)
}

/** Major-unit text ("50", "-12.5") to signed pesewas, or null. */
export function parseAmount(text: string, { signed = false } = {}): number | null {
  const trimmed = text.trim()
  const negative = signed && trimmed.startsWith('-')
  const value = parseMoney(negative ? trimmed.slice(1) : trimmed, C.MINOR_UNIT)
  return value === null ? null : negative ? -value : value
}

/** Pesewas as plain major-unit text for prefilling an input ("50.00"). */
export function majorText(amount: number): string {
  const digits = Math.round(Math.log10(C.MINOR_UNIT))
  const sign = amount < 0 ? '-' : ''
  const abs = String(Math.abs(amount)).padStart(digits + 1, '0')
  return `${sign}${abs.slice(0, -digits)}.${abs.slice(-digits)}`
}

export function fmtAge(seconds: number): string {
  if (seconds < 3600) return `${Math.max(1, Math.round(seconds / 60))} min`
  if (seconds < 86400) return `${Math.round(seconds / 3600)} h`
  return `${Math.round(seconds / 86400)} d`
}

export const ID_TYPES: Record<string, string> = {
  ghana_card: 'Ghana Card',
  passport: 'Passport',
  drivers_licence: "Driver's licence",
  voters_id: "Voter's ID",
}
