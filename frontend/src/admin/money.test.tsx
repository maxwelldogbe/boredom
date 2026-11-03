import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { AppRoutes } from '../App'
import { ToastHost } from '../components/ToastHost'
import { clearMemoryStorage } from '../lib/storage'
import { FakeWebSocket } from '../test/fakeWebSocket'
import { renderWithRoom } from '../test/render'
import type { AdminSession } from './api'

// ----- a route-based fake backend (as in admin.test.tsx) ---------------------------------

interface Call {
  path: string
  method: string
  headers: Record<string, string>
  body: unknown
}
type Reply = { status?: number; body?: unknown; blob?: Blob }

let calls: Call[] = []
let routes: Record<string, (call: Call) => Reply> = {}

function serve() {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init: RequestInit = {}) => {
      const parsed = new URL(url, 'http://localhost')
      const call = {
        path: parsed.pathname,
        method: init.method ?? 'GET',
        headers: (init.headers ?? {}) as Record<string, string>,
        body: init.body ? JSON.parse(init.body as string) : undefined,
      }
      calls.push(call)
      const handler = routes[`${call.method} ${call.path}`] ?? routes[call.path]
      if (!handler) return { ok: false, status: 404, json: async () => ({ error: { code: 'NOT_FOUND', message: 'nope' } }) }
      const { status = 200, body, blob } = handler(call)
      return { ok: status < 400, status, json: async () => body, blob: async () => blob } as Response
    }),
  )
}

const MONEY = {
  enrolled: true,
  verified: true,
  permissions: ['review_ids', 'review_deposits', 'review_withdrawals', 'adjust_balances', 'edit_merchant', 'edit_flags'],
  pending: { deposits: 2, withdrawals: 0, ids: 1, adjustments: 0 },
}

function session(money: unknown = MONEY): AdminSession {
  return {
    staff: true,
    username: 'boss',
    superuser: false,
    csrfToken: 'csrf-123',
    loginUrl: '/manage/login/',
    logoutUrl: '/manage/logout/',
    adminUrl: '/manage/',
    exports: { users: '/u.csv', sessions: '/s.csv' },
    timeZone: 'UTC',
    minGamesForRates: 5,
    money: money as AdminSession['money'],
  }
}

const deposit = {
  id: 4,
  user: { userId: 7, nickname: 'Alice', tag: 'AB12CD' },
  reference: 'NEM-ABC234',
  amountRequested: 5000,
  amountReceived: null,
  status: 'pending_review',
  paymentRef: 'TX99',
  senderNumber: '0241112222',
  merchantSnapshot: { network: 'MTN MoMo', number: '0240000001', accountName: 'Boredom Ltd' },
  createdAt: '2026-10-31T09:00:00Z',
  submittedAt: '2026-10-31T09:10:00Z',
  ageSeconds: 1200,
  firstApprovedBy: null,
  reviewedBy: null,
  reviewedAt: null,
  rejectReason: null,
  note: null,
  own: false,
}

const idRow = {
  id: 9,
  user: { userId: 7, nickname: 'Alice', tag: 'AB12CD' },
  idType: 'passport',
  fullName: 'Alice Mensah',
  last4: '7890',
  status: 'pending',
  attemptNumber: 1,
  flaggedDuplicate: false,
  createdAt: '2026-10-31T09:00:00Z',
  ageSeconds: 600,
  reviewedBy: null,
  rejectionReason: null,
  hasFront: true,
  hasBack: false,
  imagesDeletedAt: null,
  submittedDob: '1990-05-04',
}

beforeEach(() => {
  FakeWebSocket.reset()
  calls = []
  routes = { '/api/admin/session': () => ({ body: session() }) }
  serve()
})
afterEach(() => {
  vi.unstubAllGlobals()
  localStorage.clear()
  clearMemoryStorage()
})

function open(route: string) {
  return renderWithRoom(
    <>
      <AppRoutes />
      <ToastHost />
    </>,
    { route },
  )
}

describe('login and navigation', () => {
  it('asks for the code when the server needs it, then sends it', async () => {
    routes['/api/admin/session'] = () => ({ body: { ...session(), staff: false, username: null, money: null } })
    let attempts = 0
    routes['POST /api/admin/login'] = () => {
      attempts += 1
      return attempts === 1
        ? { status: 400, body: { error: { code: 'CODE_REQUIRED', message: 'Enter the code', needsCode: true } } }
        : { body: session() }
    }
    open('/admin')
    fireEvent.change(await screen.findByLabelText('Username'), { target: { value: 'boss' } })
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'pw' } })
    fireEvent.click(screen.getByRole('button', { name: 'Log in' }))
    const code = await screen.findByLabelText(/Code from your authenticator app/)
    fireEvent.change(code, { target: { value: '123456' } })
    fireEvent.click(screen.getByRole('button', { name: 'Log in' }))
    await waitFor(() => expect(attempts).toBe(2))
    expect(calls.filter((c) => c.path === '/api/admin/login')[1].body).toMatchObject({ code: '123456' })
  })

  it('shows money pages with badges only after two-factor', async () => {
    routes['/api/admin/overview'] = () => ({ status: 500, body: { error: { code: 'SERVER', message: 'x' } } })
    open('/admin')
    const nav = await screen.findByRole('navigation', { name: 'Dashboard' })
    expect(within(nav).getByRole('link', { name: /Deposits/ })).toHaveTextContent('2')
    expect(within(nav).getByLabelText('1 pending')).toBeInTheDocument()
  })

  it('unenrolled staff see only Security for money', async () => {
    routes['/api/admin/session'] = () => ({ body: session({ ...MONEY, enrolled: false, verified: false, pending: null }) })
    routes['/api/admin/overview'] = () => ({ status: 500, body: { error: { code: 'SERVER', message: 'x' } } })
    open('/admin/money/deposits')
    const nav = await screen.findByRole('navigation', { name: 'Dashboard' })
    expect(within(nav).queryByRole('link', { name: /Deposits/ })).not.toBeInTheDocument()
    expect(within(nav).getByRole('link', { name: 'Security' })).toBeInTheDocument()
    expect(await screen.findByText(/Money tools need two-factor/)).toBeInTheDocument()
    expect(calls.some((c) => c.path === '/api/admin/money/deposits')).toBe(false)
  })
})

describe('security', () => {
  it('enrols and shows backup codes once, needing a saved confirmation', async () => {
    routes['/api/admin/session'] = () => ({ body: session({ ...MONEY, enrolled: false, verified: false, pending: null }) })
    routes['POST /api/admin/2fa/setup'] = () => ({ body: { secret: 'JBSWY3DPEHPK3PXP', otpauthUri: 'otpauth://totp/Boredom:boss?secret=JBSWY3DPEHPK3PXP' } })
    routes['POST /api/admin/2fa/confirm'] = () => ({ body: { backupCodes: ['aaaa111111', 'bbbb222222'] } })
    open('/admin/security')
    fireEvent.click(await screen.findByRole('button', { name: 'Start setup' }))
    expect(await screen.findByText('JBSWY3DPEHPK3PXP')).toBeInTheDocument()
    expect(screen.getByText(/otpauth:\/\/totp/)).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Code from the app'), { target: { value: '123456' } })
    fireEvent.click(screen.getByRole('button', { name: 'Turn on two-factor' }))
    expect(await screen.findByText('aaaa111111')).toBeInTheDocument()
    const done = screen.getByRole('button', { name: 'Done' })
    expect(done).toBeDisabled()
    fireEvent.click(screen.getByLabelText('I saved these codes somewhere safe'))
    expect(done).toBeEnabled()
  })
})

describe('step-up', () => {
  it('asks for a code on STEP_UP_REQUIRED, then retries the action', async () => {
    routes['/api/admin/money/deposits'] = () => ({ body: { deposits: [deposit], dualApproval: false } })
    let approvals = 0
    routes['POST /api/admin/money/deposits/4/approve'] = () => {
      approvals += 1
      return approvals === 1
        ? { status: 403, body: { error: { code: 'STEP_UP_REQUIRED', message: 'Enter a code' } } }
        : { body: { ...deposit, status: 'approved', amountReceived: 5000 } }
    }
    routes['POST /api/admin/2fa/step-up'] = () => ({ body: { ok: true } })
    open('/admin/money/deposits')
    fireEvent.click(await screen.findByRole('button', { name: 'Open deposit NEM-ABC234' }))
    const approve = screen.getByRole('button', { name: 'Approve and credit' })
    expect(approve).toBeDisabled()
    fireEvent.click(screen.getByLabelText('I verified this payment in the receiving account'))
    expect(screen.getByLabelText('Amount received (GHS)')).toHaveValue('50.00')
    fireEvent.click(approve)
    const dialog = await screen.findByRole('dialog', { name: "Confirm it's you" })
    fireEvent.change(within(dialog).getByLabelText('Code'), { target: { value: '654321' } })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Confirm' }))
    await waitFor(() => expect(approvals).toBe(2))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(calls.find((c) => c.path === '/api/admin/2fa/step-up')?.body).toEqual({ code: '654321' })
    const sent = calls.filter((c) => c.path === '/api/admin/money/deposits/4/approve')[1]
    expect(sent.body).toEqual({ receivedAmount: 5000, verifiedInAccount: true, note: '' })
    expect(sent.headers['X-CSRFToken']).toBe('csrf-123')
  })
})

describe('ID review', () => {
  it('loads photos through the authenticated endpoint as a blob URL, never a public URL', async () => {
    const createObjectURL = vi.fn(() => 'blob:local-1')
    vi.stubGlobal('URL', Object.assign(URL, { createObjectURL, revokeObjectURL: vi.fn() }))
    routes['/api/admin/ids'] = () => ({ body: { ids: [idRow] } })
    routes['/api/admin/ids/9'] = () => ({ body: idRow })
    routes['/api/admin/ids/9/image/front'] = () => ({ blob: new Blob(['png'], { type: 'image/png' }) })
    open('/admin/money/ids')
    fireEvent.click(await screen.findByRole('button', { name: 'Open ID 9' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Show front photo' }))
    const img = await screen.findByRole('img', { name: 'ID front' })
    expect(img).toHaveAttribute('src', 'blob:local-1')
    expect(calls.some((c) => c.path === '/api/admin/ids/9/image/front')).toBe(true)
    expect(document.body.innerHTML).not.toContain('/image/front"')
  })
})

describe('overview', () => {
  it('shows the red warning banner', async () => {
    routes['/api/admin/money/overview'] = () => ({
      body: {
        range: { key: '7d', label: 'Last 7 days' },
        ranges: [{ key: '7d', label: 'Last 7 days' }],
        liabilities: 700000,
        depositsTotal: 0,
        withdrawalsTotal: 0,
        pending: MONEY.pending,
        latestReport: null,
        ledgerOk: false,
        warnings: ['report_stale', 'ledger_mismatch'],
        lastMerchantChange: null,
        flags: { depositsEnabled: true, withdrawalsEnabled: true, stakingEnabled: false },
        dualApproval: false,
      },
    })
    open('/admin/money')
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('The ledger check failed')
    expect(alert).toHaveTextContent('No reconciliation report')
    expect(screen.getByText(/7,000\.00/)).toBeInTheDocument()
  })
})
