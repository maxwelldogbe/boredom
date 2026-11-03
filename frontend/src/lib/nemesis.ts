/**
 * Nemesis (core/PROTOCOL.md section 14): the real-money wallet client. The server decides every
 * balance, limit, fee and eligibility; this file only sends requests and formats what comes back.
 * All amounts are integers in the minor unit (pesewas).
 */
import { getAuthToken } from './account'
import { C } from './constants'
import { apiUrl } from './endpoints'

export type IdState = 'none' | 'pending' | 'approved' | 'rejected' | 'rejected_final'

export interface NemesisStatus {
  enabled: boolean
  active?: boolean
  rulesVersion?: number
  eligibility?: {
    accountAgeOk: boolean
    hoursLeft: number
    gamesPlayed: number
    gamesNeeded: number
    idState: IdState
  }
  idState?: IdState
  attemptsLeft?: number
  rejectionReason?: string | null
  retentionDays?: number
  excluded?: boolean
}

export interface Payout {
  method: 'mobile_money' | 'bank'
  network: string
  number: string
  accountName: string
  effectiveAt: string | null
  effective: boolean
}

export interface PendingRaise {
  depositDailyLimit?: number
  deposit30dLimit?: number
  effectiveAt: string
}

export interface Wallet {
  currency: string
  minorUnit: number
  balance: number
  held: number
  limits: {
    platform: {
      depositMin: number
      depositMax: number
      depositDaily: number
      deposit30d: number
      withdrawMin: number
      withdrawDailyCap: number
    }
    player: { depositDaily: number; deposit30d: number }
    pendingRaise: PendingRaise | null
  }
  exclusion: { active: boolean; permanent: boolean; until: string | null }
  payout: Payout | null
  flags: { depositsEnabled: boolean; withdrawalsEnabled: boolean; stakingEnabled: boolean }
}

export interface PaymentDetails {
  method: string
  network: string
  number: string
  accountName: string
}

export type DepositStatus = 'awaiting_payment' | 'pending_review' | 'approved' | 'rejected' | 'expired' | 'cancelled'

export interface Deposit {
  id: number
  reference: string
  amount: number
  amountReceived: number | null
  status: DepositStatus
  paymentDetails: PaymentDetails
  paymentRef: string | null
  senderNumber: string
  createdAt: string
  expiresAt: string
  submittedAt: string | null
  rejectReason: string | null
}

export type WithdrawalStatus = 'pending_review' | 'approved' | 'paid' | 'rejected' | 'cancelled'

export interface Withdrawal {
  id: number
  amount: number
  status: WithdrawalStatus
  createdAt: string
  eligibleAt: string
  payout: { method: string; network: string; number: string; accountName: string }
  payoutReference: string | null
  paidAt: string | null
  rejectReason: string | null
}

export interface LedgerLine {
  id: number
  kind: 'deposit' | 'withdrawal_hold' | 'withdrawal_paid' | 'withdrawal_refund' | 'adjustment'
  amount: number
  balanceAfter: number
  account: 'available' | 'held'
  createdAt: string
}

/** A failed Nemesis request: `code` from the server (or NETWORK / SERVER), `extra` keys too. */
export class NemesisError extends Error {
  readonly code: string
  readonly fields: Record<string, string>
  readonly extra: Record<string, unknown>
  constructor(code: string, message: string, fields: Record<string, string> = {}, extra: Record<string, unknown> = {}) {
    super(message)
    this.code = code
    this.fields = fields
    this.extra = extra
  }
}

const MESSAGES: Record<string, string> = {
  NETWORK: "Can't reach the server. Check your connection and try again.",
  SERVER: 'Something went wrong. Please try again.',
  UNAUTHORIZED: 'Please log in again.',
  RATE_LIMITED: 'Too many tries. Wait a little and try again.',
  NOT_FOUND: 'This is not available right now.',
  NOT_ACTIVE: 'Turn on Nemesis first.',
  NOT_ELIGIBLE: "You can't turn on Nemesis yet.",
  ID_REQUIRED: 'Verify your age first.',
  ID_ALREADY_USED: 'This ID is already used by another account.',
  EXCLUDED: "You're taking a break, so this is blocked for now.",
  ALREADY_ACTIVE: 'Nemesis is already on.',
  LIMIT_REACHED: "That's over your limit.",
  DUPLICATE_REFERENCE: 'That transaction ID was already used.',
  INSUFFICIENT_FUNDS: "You don't have enough money for that.",
  PAYOUT_NOT_SET: 'Add where we should send your money first.',
  PAYOUT_PENDING: "Your new payout details aren't active yet.",
  WITHDRAWAL_PENDING: 'You already have a withdrawal waiting.',
  DEPOSIT_OPEN: 'You already have a deposit in progress.',
  FEATURE_DISABLED: 'This is paused right now. Try again later.',
  STEP_UP_REQUIRED: 'Please confirm with a code.',
  FORBIDDEN: "You can't do that.",
  REQUEST_NOT_FOUND: "We couldn't find that request.",
  INVALID_STATE: "That can't be done right now. Refresh and try again.",
  INVALID_INPUT: 'Some fields need fixing.',
  HAS_FUNDS: 'Withdraw your balance and finish open requests first.',
}

/** A plain message for any error code. */
export function nemesisMessage(err: unknown): string {
  if (err instanceof NemesisError) return MESSAGES[err.code] ?? err.message ?? MESSAGES.SERVER
  return MESSAGES.SERVER
}

export function newIdempotencyKey(): string {
  const c = globalThis.crypto
  if (c?.randomUUID) return c.randomUUID()
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`
}

type Method = 'GET' | 'POST' | 'PUT'

function token(): string {
  const value = getAuthToken()
  if (!value) throw new NemesisError('UNAUTHORIZED', MESSAGES.UNAUTHORIZED)
  return value
}

function toError(status: number, data: unknown): NemesisError {
  const error = (data as { error?: Record<string, unknown> } | null)?.error ?? {}
  const { code, message, fields, ...extra } = error as {
    code?: string
    message?: string
    fields?: Record<string, string>
  }
  return new NemesisError(code ?? (status >= 500 ? 'SERVER' : 'INVALID_INPUT'), message ?? MESSAGES.SERVER, fields ?? {}, extra)
}

/** JSON request; every POST/PUT carries an Idempotency-Key (pass the same key to retry). */
export async function nemesisCall<T>(method: Method, path: string, body?: unknown, key?: string): Promise<T> {
  const headers: Record<string, string> = { Accept: 'application/json', Authorization: `Bearer ${token()}` }
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  if (method !== 'GET') headers['Idempotency-Key'] = key ?? newIdempotencyKey()
  let response: Response
  try {
    response = await fetch(apiUrl(path), { method, headers, body: body === undefined ? undefined : JSON.stringify(body) })
  } catch {
    throw new NemesisError('NETWORK', MESSAGES.NETWORK)
  }
  const data: unknown = await response.json().catch(() => null)
  if (response.ok) return data as T
  throw toError(response.status, data)
}

export const fetchStatus = () => nemesisCall<NemesisStatus>('GET', '/api/nemesis/status')
export const fetchWallet = () => nemesisCall<Wallet>('GET', '/api/wallet')
export const activate = (rulesVersion: number) =>
  nemesisCall<NemesisStatus>('POST', '/api/nemesis/activate', { confirmAge: true, acceptRules: true, rulesVersion })
export const deactivate = () => nemesisCall<NemesisStatus>('POST', '/api/nemesis/deactivate', {})
export const fetchEntries = (cursor?: number | null) =>
  nemesisCall<{ entries: LedgerLine[]; nextCursor: number | null }>('GET', `/api/wallet/entries${cursor ? `?cursor=${cursor}` : ''}`)
export const fetchDeposits = () => nemesisCall<{ deposits: Deposit[]; open: Deposit | null }>('GET', '/api/wallet/deposits')
export const createDeposit = (amount: number, key: string) => nemesisCall<Deposit>('POST', '/api/wallet/deposits', { amount }, key)
export const submitDeposit = (id: number, paymentRef: string, senderNumber: string, key: string) =>
  nemesisCall<Deposit>('POST', `/api/wallet/deposits/${id}/submit`, { paymentRef, senderNumber }, key)
export const cancelDeposit = (id: number) => nemesisCall<Deposit>('POST', `/api/wallet/deposits/${id}/cancel`, {})
export const fetchWithdrawals = () => nemesisCall<{ withdrawals: Withdrawal[] }>('GET', '/api/wallet/withdrawals')
export const createWithdrawal = (amount: number, key: string) =>
  nemesisCall<Withdrawal>('POST', '/api/wallet/withdrawals', { amount }, key)
export const cancelWithdrawal = (id: number) => nemesisCall<Withdrawal>('POST', `/api/wallet/withdrawals/${id}/cancel`, {})
export const setPayout = (body: { method: string; network: string; number: string; accountName: string; password: string }) =>
  nemesisCall<{ payout: Payout }>('POST', '/api/wallet/payout-destination', body)
export const setLimits = (depositDailyLimit: number, deposit30dLimit: number) =>
  nemesisCall<Wallet['limits']>('PUT', '/api/wallet/limits', { depositDailyLimit, deposit30dLimit })
export const takeBreak = (days: 7 | 30 | 'permanent') =>
  nemesisCall<{ exclusion: Wallet['exclusion'] }>('POST', '/api/wallet/exclude', { days })

/** POST /api/nemesis/id as multipart, reporting upload progress (0..1). */
export function uploadId(form: FormData, onProgress: (fraction: number) => void): Promise<NemesisStatus> {
  return new Promise((resolve, reject) => {
    let auth: string
    try {
      auth = token()
    } catch (err) {
      reject(err)
      return
    }
    const xhr = new XMLHttpRequest()
    xhr.open('POST', apiUrl('/api/nemesis/id'))
    xhr.setRequestHeader('Authorization', `Bearer ${auth}`)
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress(e.loaded / e.total)
    xhr.onerror = () => reject(new NemesisError('NETWORK', MESSAGES.NETWORK))
    xhr.onload = () => {
      const data: unknown = (() => {
        try {
          return JSON.parse(xhr.responseText)
        } catch {
          return null
        }
      })()
      if (xhr.status >= 200 && xhr.status < 300) resolve(data as NemesisStatus)
      else reject(toError(xhr.status, data))
    }
    xhr.send(form)
  })
}

// ----- formatting and input (display only; the server checks every amount) ---------------

export function formatMoney(amount: number, currency: string, minorUnit: number): string {
  const digits = Math.round(Math.log10(minorUnit))
  return new Intl.NumberFormat(undefined, {
    style: 'currency',
    currency,
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(amount / minorUnit)
}

/** "50" or "50.5" or "50.50" (major units) to an integer of minor units; null if not valid. */
export function parseMoney(text: string, minorUnit: number): number | null {
  const digits = Math.round(Math.log10(minorUnit))
  const match = text.trim().replace(/,/g, '').match(new RegExp(`^(\\d{1,9})(?:\\.(\\d{1,${digits}}))?$`))
  if (!match) return null
  const fraction = (match[2] ?? '').padEnd(digits, '0')
  return Number(match[1]) * minorUnit + Number(fraction || '0')
}

/** Early feedback only: JPEG or PNG and not larger than ID_MAX_BYTES (the server rechecks). */
export function idFileError(file: File | null | undefined, required: boolean): string | null {
  if (!file) return required ? 'Add a photo of the front of your ID.' : null
  if (!['image/jpeg', 'image/png'].includes(file.type)) return 'Use a JPEG or PNG photo.'
  if (file.size > C.ID_MAX_BYTES) return `The photo must be ${Math.floor(C.ID_MAX_BYTES / 1048576)} MB or smaller.`
  return null
}

export const ID_TYPE_LABELS: Record<string, string> = {
  ghana_card: 'Ghana Card',
  passport: 'Passport',
  drivers_licence: "Driver's licence",
  voters_id: "Voter's ID",
}

export function localTime(iso: string | null | undefined): string {
  return iso ? new Date(iso).toLocaleString() : ''
}
