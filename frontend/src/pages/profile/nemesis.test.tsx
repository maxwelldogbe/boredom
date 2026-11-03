import { act, fireEvent, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { AppRoutes } from '../../App'
import { ToastHost } from '../../components/ToastHost'
import { adoptSession } from '../../lib/account'
import { NemesisError, nemesisMessage, parseMoney } from '../../lib/nemesis'
import { clearMemoryStorage } from '../../lib/storage'
import { fakeFetch } from '../../test/fakeFetch'
import { FakeWebSocket } from '../../test/fakeWebSocket'
import { profileFx } from '../../test/fixtures'
import { renderWithRoom } from '../../test/render'
import { DEPOSIT_POLL_MS } from './nemesis/AddFunds'

let api: ReturnType<typeof fakeFetch>
const STATUS = '/api/nemesis/status'
const WALLET = '/api/wallet'
const DEPOSITS = '/api/wallet/deposits'
const WITHDRAWALS = '/api/wallet/withdrawals'

const eligibility = { accountAgeOk: true, hoursLeft: 0, gamesPlayed: 9, gamesNeeded: 0, idState: 'approved' }
const status = (over: Record<string, unknown> = {}) => ({
  enabled: true,
  active: false,
  rulesVersion: 1,
  eligibility,
  idState: 'approved',
  attemptsLeft: 2,
  rejectionReason: null,
  retentionDays: 30,
  excluded: false,
  ...over,
})
const wallet = (over: Record<string, unknown> = {}) => ({
  currency: 'GHS',
  minorUnit: 100,
  balance: 12345,
  held: 0,
  limits: {
    platform: { depositMin: 1000, depositMax: 100000, depositDaily: 200000, deposit30d: 1000000, withdrawMin: 2000, withdrawDailyCap: 100000 },
    player: { depositDaily: 200000, deposit30d: 1000000 },
    pendingRaise: null,
  },
  exclusion: { active: false, permanent: false, until: null },
  payout: null,
  flags: { depositsEnabled: true, withdrawalsEnabled: true, stakingEnabled: false },
  ...over,
})
const deposit = (over: Record<string, unknown> = {}) => ({
  id: 7,
  reference: 'NEM-ABC234',
  amount: 5000,
  amountReceived: null,
  status: 'awaiting_payment',
  paymentDetails: { method: 'mobile_money', network: 'MTN MoMo', number: '0240000001', accountName: 'Boredom Ltd' },
  paymentRef: null,
  senderNumber: '',
  createdAt: '2026-10-31T10:00:00Z',
  expiresAt: '2026-10-31T11:00:00Z',
  submittedAt: null,
  rejectReason: null,
  ...over,
})

beforeEach(() => {
  FakeWebSocket.reset()
  api = fakeFetch()
})
afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
  localStorage.clear()
  clearMemoryStorage()
})

async function openProfile(nemesis: unknown, extra: Array<[string, unknown]> = []) {
  adoptSession({ token: 'jwt-1', profile: profileFx.me.profile, stats: profileFx.me.stats })
  api.reply(200, profileFx.me)
  api.route(STATUS, 200, nemesis)
  for (const [url, body] of extra) api.route(url, 200, body)
  renderWithRoom(
    <>
      <AppRoutes />
      <ToastHost />
    </>,
    { route: '/profile' },
  )
  await screen.findByRole('heading', { level: 1, name: profileFx.me.profile.nickname })
  await act(async () => {
    await Promise.resolve()
  })
}

const section = () => screen.getByRole('region', { name: 'Nemesis' })
const button = (name: string | RegExp) => within(section()).findByRole('button', { name })
const posts = (url: string) => api.meCalls.filter((c) => c.url === url && c.method !== 'GET')

describe('section states', () => {
  it('shows nothing when the server has Nemesis off', async () => {
    await openProfile({ enabled: false })
    expect(screen.queryByRole('region', { name: 'Nemesis' })).not.toBeInTheDocument()
    expect(document.body.textContent).not.toContain('Nemesis')
  })

  it('offers age verification without an ID', async () => {
    await openProfile(status({ idState: 'none', eligibility: { ...eligibility, idState: 'none' } }))
    expect(await button('Verify your age')).toBeVisible()
  })

  it('shows the reason and tries left after a rejection, and a plain final message', async () => {
    await openProfile(status({ idState: 'rejected', rejectionReason: 'Blurry photo', attemptsLeft: 1 }))
    expect(await within(section()).findByText(/Blurry photo/)).toBeInTheDocument()
    expect(await button('Try again (1 try left)')).toBeVisible()
  })

  it('shows the server numbers on a disabled button when not eligible', async () => {
    await openProfile(status({ eligibility: { ...eligibility, gamesNeeded: 3 } }), [[WALLET, wallet({ balance: 0 })]])
    expect(await button('Play 3 more games')).toBeDisabled()
  })

  it('turns on only with both boxes ticked and gives no credit', async () => {
    await openProfile(status(), [
      [WALLET, wallet({ balance: 0 })],
      ['/api/nemesis/activate', status({ active: true })],
      [WALLET, wallet({ balance: 0 })],
    ])
    fireEvent.click(await button('Turn on Nemesis'))
    const dialog = screen.getByRole('dialog', { name: 'Turn on Nemesis' })
    expect(within(dialog).getByRole('button', { name: 'Cancel' })).toHaveFocus()
    const turnOn = within(dialog).getByRole('button', { name: 'Turn on' })
    expect(turnOn).toBeDisabled()
    fireEvent.click(within(dialog).getByLabelText('I am 18 or older'))
    fireEvent.click(within(dialog).getByLabelText('I have read the rules'))
    fireEvent.click(turnOn)
    expect(await button('Add funds')).toBeVisible()
    expect(posts('/api/nemesis/activate')[0].body).toEqual({ confirmAge: true, acceptRules: true, rulesVersion: 1 })
  })

  it('shows the balance and every action when on', async () => {
    await openProfile(status({ active: true }), [[WALLET, wallet()]])
    expect(await within(section()).findByText(/123\.45/)).toBeInTheDocument()
    for (const name of ['Add funds', 'Withdraw', 'History', 'Limits', 'Take a break', 'Turn off']) expect(await button(name)).toBeVisible()
  })

  it('shows Retry when the wallet fails to load', async () => {
    api.route(WALLET, 500, { error: { code: 'SERVER', message: 'x' } })
    await openProfile(status({ active: true }), [[WALLET, wallet()]])
    fireEvent.click(await button('Retry'))
    expect(await button('Add funds')).toBeVisible()
  })
})

describe('ID form', () => {
  it('checks fields and the photo type before uploading', async () => {
    await openProfile(status({ idState: 'none', eligibility: { ...eligibility, idState: 'none' } }))
    fireEvent.click(await button('Verify your age'))
    expect(within(section()).getByText(/deleted 30 days after review/)).toBeInTheDocument()
    const gif = new File(['GIF89a'], 'id.gif', { type: 'image/gif' })
    fireEvent.change(within(section()).getByLabelText('Front photo'), { target: { files: [gif] } })
    fireEvent.click(within(section()).getByRole('button', { name: 'Send for review' }))
    expect(within(section()).getByText('Enter your name as it appears on the ID.')).toBeInTheDocument()
    expect(within(section()).getByText('Use a JPEG or PNG photo.')).toBeInTheDocument()
  })
})

describe('add funds', () => {
  it('creates a request, shows the reference and waits, then sees the approval', async () => {
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
    await openProfile(status({ active: true }), [
      [WALLET, wallet()],
      [DEPOSITS, { deposits: [], open: null }],
      [DEPOSITS, deposit()],
      ['/api/wallet/deposits/7/submit', deposit({ status: 'pending_review', paymentRef: 'TX1' })],
    ])
    fireEvent.click(await button('Add funds'))
    fireEvent.change(await within(section()).findByLabelText('Amount (GHS)'), { target: { value: '50' } })
    fireEvent.click(within(section()).getByRole('button', { name: 'Continue' }))
    expect(await within(section()).findByText('NEM-ABC234')).toBeInTheDocument()
    expect(within(section()).getByText('Put this reference in the payment note.')).toBeInTheDocument()
    const created = posts(DEPOSITS)[0]
    expect(created.body).toEqual({ amount: 5000 })
    expect(created.headers['Idempotency-Key']).toBeTruthy()
    fireEvent.change(within(section()).getByLabelText('Transaction ID'), { target: { value: 'TX1' } })
    fireEvent.change(within(section()).getByLabelText('Number you paid from'), { target: { value: '0241112222' } })
    fireEvent.click(within(section()).getByRole('button', { name: "I've paid" }))
    expect(await within(section()).findByText('Waiting for confirmation')).toBeInTheDocument()
    api.route(DEPOSITS, 200, { deposits: [deposit({ status: 'approved', amountReceived: 5000 })], open: null })
    await act(async () => {
      vi.advanceTimersByTime(DEPOSIT_POLL_MS)
    })
    expect(await within(section()).findByText(/Approved\./)).toBeInTheDocument()
  })

  it('resumes an open request after a refresh', async () => {
    await openProfile(status({ active: true }), [
      [WALLET, wallet()],
      [DEPOSITS, { deposits: [deposit()], open: deposit() }],
    ])
    fireEvent.click(await button('Add funds'))
    expect(await within(section()).findByText('NEM-ABC234')).toBeInTheDocument()
  })

  it('maps a limit error to a plain message with the remaining amount', async () => {
    await openProfile(status({ active: true }), [
      [WALLET, wallet()],
      [DEPOSITS, { deposits: [], open: null }],
    ])
    api.route(DEPOSITS, 409, { error: { code: 'LIMIT_REACHED', message: 'x', remaining: 2000 } })
    fireEvent.click(await button('Add funds'))
    fireEvent.change(await within(section()).findByLabelText('Amount (GHS)'), { target: { value: '500' } })
    fireEvent.click(within(section()).getByRole('button', { name: 'Continue' }))
    expect(await within(section()).findByText(/up to .*20\.00 right now/)).toBeInTheDocument()
  })
})

describe('withdraw', () => {
  it('sets a payout with the password, then confirms the amount with the masked number', async () => {
    const payout = { method: 'mobile_money', network: 'MTN MoMo', number: '•••234', accountName: 'Ama', effectiveAt: '2026-10-31T10:00:00Z', effective: true }
    await openProfile(status({ active: true }), [
      [WALLET, wallet()],
      [WITHDRAWALS, { withdrawals: [] }],
      ['/api/wallet/payout-destination', { payout }],
      [WITHDRAWALS, { id: 3, amount: 5000, status: 'pending_review', createdAt: '2026-10-31T10:00:00Z', eligibleAt: '2026-11-01T10:00:00Z', payout, payoutReference: null, paidAt: null, rejectReason: null }],
    ])
    fireEvent.click(await button('Withdraw'))
    fireEvent.change(await within(section()).findByLabelText('Phone number'), { target: { value: '0245551234' } })
    fireEvent.change(within(section()).getByLabelText('Account name'), { target: { value: 'Ama' } })
    fireEvent.change(within(section()).getByLabelText('Your password'), { target: { value: 'secret pass' } })
    fireEvent.click(within(section()).getByRole('button', { name: 'Save payout details' }))
    fireEvent.change(await within(section()).findByLabelText('Amount (GHS)'), { target: { value: '50' } })
    fireEvent.click(within(section()).getByRole('button', { name: 'Withdraw' }))
    const dialog = screen.getByRole('dialog', { name: 'Withdraw?' })
    expect(dialog).toHaveTextContent('•••234')
    expect(within(dialog).getByRole('button', { name: 'Cancel' })).toHaveFocus()
    fireEvent.click(within(dialog).getByRole('button', { name: 'Withdraw' }))
    expect(await within(section()).findByText(/Waiting for review/)).toBeInTheDocument()
    expect(posts('/api/wallet/payout-destination')[0].body).toMatchObject({ password: 'secret pass' })
    expect(posts(WITHDRAWALS)[0].body).toEqual({ amount: 5000 })
  })
})

describe('limits and breaks', () => {
  it('shows a pending raise and its time', async () => {
    const limits = wallet().limits
    await openProfile(status({ active: true }), [
      [WALLET, wallet()],
      ['/api/wallet/limits', { ...limits, player: { depositDaily: 5000, deposit30d: 1000000 }, pendingRaise: { depositDailyLimit: 9000, effectiveAt: '2026-11-01T10:00:00Z' } }],
    ])
    fireEvent.click(await button('Limits'))
    fireEvent.change(await within(section()).findByLabelText('Daily limit (GHS)'), { target: { value: '90' } })
    fireEvent.click(within(section()).getByRole('button', { name: 'Save limits' }))
    expect(await within(section()).findByText(/Raise waiting/)).toHaveTextContent('90.00')
  })

  it('explains what a break blocks before starting it', async () => {
    await openProfile(status({ active: true }), [
      [WALLET, wallet()],
      ['/api/wallet/exclude', { exclusion: { active: true, permanent: true, until: null } }],
      [WALLET, wallet()],
    ])
    fireEvent.click(await button('Take a break'))
    fireEvent.click(await button('Permanently'))
    const dialog = screen.getByRole('dialog', { name: 'Take a permanent break?' })
    expect(dialog).toHaveTextContent('Still allowed: withdrawing')
    expect(dialog).toHaveTextContent('Only our team can lift it.')
    expect(within(dialog).getByRole('button', { name: 'Cancel' })).toHaveFocus()
    fireEvent.click(within(dialog).getByRole('button', { name: 'Start break' }))
    await act(async () => {
      await Promise.resolve()
    })
    expect(posts('/api/wallet/exclude')[0].body).toEqual({ days: 'permanent' })
  })

  it('turn off says the balance is kept', async () => {
    await openProfile(status({ active: true }), [[WALLET, wallet()]])
    fireEvent.click(await button('Turn off'))
    expect(screen.getByRole('dialog', { name: 'Turn off Nemesis?' })).toHaveTextContent('Your balance and history are kept. You can still withdraw.')
  })
})

describe('helpers', () => {
  it('maps every error code to a plain message', () => {
    for (const code of ['NOT_ACTIVE', 'EXCLUDED', 'LIMIT_REACHED', 'DUPLICATE_REFERENCE', 'INSUFFICIENT_FUNDS', 'PAYOUT_PENDING', 'NETWORK']) {
      expect(nemesisMessage(new NemesisError(code, 'raw server text'))).not.toBe('raw server text')
    }
  })

  it('parses money without floats', () => {
    expect(parseMoney('50', 100)).toBe(5000)
    expect(parseMoney('0.5', 100)).toBe(50)
    expect(parseMoney('19.99', 100)).toBe(1999)
    expect(parseMoney('1.234', 100)).toBeNull()
    expect(parseMoney('abc', 100)).toBeNull()
  })
})

describe('no Nemesis text outside /profile', () => {
  it.each(['/', '/about'])('%s', async (route) => {
    adoptSession({ token: 'jwt-1', profile: profileFx.me.profile, stats: profileFx.me.stats })
    api.route(STATUS, 200, status({ active: true }))
    renderWithRoom(<AppRoutes />, { route })
    await act(async () => {
      await Promise.resolve()
    })
    expect(document.body.textContent).not.toMatch(/nemesis/i)
    expect(api.meCalls.some((c) => c.url === STATUS)).toBe(false)
  })
})
