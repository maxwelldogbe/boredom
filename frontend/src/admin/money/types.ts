/** Shapes returned by the Nemesis staff API (core/PROTOCOL.md section 15). Amounts are pesewas. */

export interface Person {
  userId: number
  nickname: string
  tag: string | null
}

export interface DepositRow {
  id: number
  user: Person | null
  reference: string
  amountRequested: number
  amountReceived: number | null
  status: string
  paymentRef: string | null
  senderNumber: string
  merchantSnapshot: { network?: string; number?: string; accountName?: string }
  createdAt: string
  submittedAt: string | null
  ageSeconds: number
  firstApprovedBy: string | null
  reviewedBy: string | null
  reviewedAt: string | null
  rejectReason: string | null
  note: string | null
  own: boolean
}

export interface WithdrawalRow {
  id: number
  user: Person | null
  idName: string | null
  amount: number
  status: string
  payoutSnapshot: { method?: string; network?: string; number?: string; accountName?: string }
  createdAt: string
  eligibleAt: string
  eligible: boolean
  ageSeconds: number
  firstApprovedBy: string | null
  reviewedBy: string | null
  payoutReference: string | null
  paidBy: string | null
  paidAt: string | null
  rejectReason: string | null
  own: boolean
}

export interface IdRow {
  id: number
  user: Person | null
  idType: string
  fullName: string
  last4: string
  status: string
  attemptNumber: number
  flaggedDuplicate: boolean
  createdAt: string
  ageSeconds: number
  reviewedBy: string | null
  rejectionReason: string | null
  hasFront: boolean
  hasBack: boolean
  imagesDeletedAt: string | null
  submittedDob?: string | null
}

export interface ReportRow {
  id: number
  date: string
  reportedBalance: number
  ledgerLiabilities: number
  difference: number
  ok: boolean
  enteredBy: string | null
  createdAt: string
}

export interface LedgerCheck {
  ok: boolean
  entriesSum: number
  unbalancedTransactions: number
  mismatchedAccounts: unknown[]
  liabilities: number
}

export interface MoneyOverview {
  range: { key: string; label: string }
  ranges: Array<{ key: string; label: string }>
  liabilities: number
  depositsTotal: number
  withdrawalsTotal: number
  pending: { deposits: number; withdrawals: number; ids: number; adjustments: number }
  latestReport: ReportRow | null
  ledgerOk: boolean
  warnings: string[]
  lastMerchantChange: string | null
  flags: Flags
  dualApproval: boolean
}

export interface Flags {
  depositsEnabled: boolean
  withdrawalsEnabled: boolean
  stakingEnabled: boolean
}

export interface MerchantRow {
  id: number
  method: string
  network: string
  number: string
  accountName: string
  active: boolean
  pending: boolean
  createdBy: string | null
  approvedBy: string | null
  createdAt: string
  activatedAt: string | null
}

export interface AdjustmentRow {
  id: number
  user: Person | null
  amount: number
  reason: string
  status: string
  proposedBy: string | null
  approvedBy: string | null
  createdAt: string
  decidedAt: string | null
}

export interface UserMoney {
  verification: { idState: string; attemptsLeft: number; rejectionReason: string | null } | null
  wallet: {
    balance: number
    held: number
    active: boolean
    exclusion: { active: boolean; permanent: boolean; until: string | null }
  } | null
  canRemoveExclusion: boolean
}
