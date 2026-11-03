import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react'
import { Link, NavLink, Navigate, Route, Routes } from 'react-router-dom'
import { Button } from '../components/Button'
import { Logo } from '../components/Logo'
import { AdminApiError, getSession, login, logout, type AdminSession } from './api'
import ActivityPage from './pages/ActivityPage'
import GameDetailPage from './pages/GameDetailPage'
import GamesPage from './pages/GamesPage'
import LeaderboardsPage from './pages/LeaderboardsPage'
import OverviewPage from './pages/OverviewPage'
import RecoveryPage from './pages/RecoveryPage'
import UserDetailPage from './pages/UserDetailPage'
import UsersPage from './pages/UsersPage'
import SecurityPage from './pages/SecurityPage'
import AdjustmentsPage from './pages/money/AdjustmentsPage'
import AuditPage from './pages/money/AuditPage'
import DepositsPage from './pages/money/DepositsPage'
import IdsPage from './pages/money/IdsPage'
import MoneyOverviewPage from './pages/money/MoneyOverviewPage'
import ReconcilePage from './pages/money/ReconcilePage'
import SettingsPage from './pages/money/SettingsPage'
import WithdrawalsPage from './pages/money/WithdrawalsPage'
import { StepUpProvider } from './money/StepUpProvider'
import { AdminSessionContext, type AdminSessionValue } from './session'
import './admin.css'

const NAV = [
  { to: '/admin', label: 'Overview', end: true },
  { to: '/admin/games', label: 'Games' },
  { to: '/admin/users', label: 'Users' },
  { to: '/admin/leaderboards', label: 'Leaderboards' },
  { to: '/admin/activity', label: 'Activity' },
  { to: '/admin/recovery', label: 'Account recovery' },
]

type Badge = 'deposits' | 'withdrawals' | 'ids'

/** Nemesis pages, shown once the session passed two-factor. */
const MONEY_NAV: Array<{ to: string; label: string; end?: boolean; badge?: Badge }> = [
  { to: '/admin/money', label: 'Money', end: true },
  { to: '/admin/money/deposits', label: 'Deposits', badge: 'deposits' },
  { to: '/admin/money/withdrawals', label: 'Withdrawals', badge: 'withdrawals' },
  { to: '/admin/money/ids', label: 'IDs', badge: 'ids' },
  { to: '/admin/money/reconcile', label: 'Reconciliation' },
  { to: '/admin/money/adjustments', label: 'Adjustments' },
  { to: '/admin/money/settings', label: 'Money settings' },
  { to: '/admin/money/audit', label: 'Money audit' },
]

/** The staff dashboard (lazy-loaded at /admin/*). Has its own login form (staff accounts only). */
export default function AdminApp() {
  const [session, setSession] = useState<AdminSession | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(() => {
    getSession()
      .then((s) => {
        setSession(s)
        setError(null)
      })
      .catch((err: unknown) => setError(err instanceof AdminApiError ? err.message : 'Something went wrong.'))
  }, [])

  useEffect(load, [load])

  const value = useMemo<AdminSessionValue | null>(
    () => (session ? { session, onUnauthorized: load, refresh: load } : null),
    [session, load],
  )

  if (error)
    return (
      <main className="page stack admin-gate">
        <h1>Admin</h1>
        <p className="field__error" role="alert">
          {error}
        </p>
        <Button onClick={load}>Try again</Button>
      </main>
    )
  if (!session || !value)
    return (
      <main className="page admin-gate">
        <p className="muted">Loading…</p>
      </main>
    )
  if (!session.staff) return <StaffLogin session={session} onLoggedIn={setSession} />

  return (
    <AdminSessionContext.Provider value={value}>
      <div className="admin">
        <header className="admin__header">
          <Link to="/admin" className="admin__brand" aria-label="Boredom admin, overview">
            <Logo size={28} />
            <span className="admin__brand-text">Admin</span>
          </Link>
          <nav className="admin__nav" aria-label="Dashboard">
            {NAV.map((item) => (
              <NavLink key={item.to} to={item.to} end={item.end} className="admin__nav-link">
                {item.label}
              </NavLink>
            ))}
            {session.money?.verified &&
              MONEY_NAV.map((item) => {
                const count = item.badge ? (session.money?.pending?.[item.badge] ?? 0) : 0
                return (
                  <NavLink key={item.to} to={item.to} end={item.end} className="admin__nav-link">
                    {item.label}
                    {count > 0 && (
                      <span className="nav-badge" aria-label={`${count} pending`}>
                        {count}
                      </span>
                    )}
                  </NavLink>
                )
              })}
            {session.money && (
              <NavLink to="/admin/security" className="admin__nav-link">
                Security
              </NavLink>
            )}
          </nav>
          <div className="admin__me">
            <span className="muted">{session.username}</span>
            <button
              type="button"
              className="btn btn--ghost admin__logout"
              onClick={async () => {
                await logout(session)
                load()
              }}
            >
              Log out
            </button>
          </div>
        </header>
        <main className="admin__main">
          <StepUpProvider>
            <Routes>
              <Route index element={<OverviewPage />} />
              <Route path="games" element={<GamesPage />} />
              <Route path="games/:gameId" element={<GameDetailPage />} />
              <Route path="users" element={<UsersPage />} />
              <Route path="users/u/:userId" element={<UserDetailPage kind="registered" />} />
              <Route path="users/g/:guestKey" element={<UserDetailPage kind="guest" />} />
              <Route path="leaderboards" element={<LeaderboardsPage />} />
              <Route path="activity" element={<ActivityPage />} />
              <Route path="recovery" element={<RecoveryPage />} />
              <Route path="security" element={<SecurityPage />} />
              <Route path="money" element={<MoneyOverviewPage />} />
              <Route path="money/deposits" element={<DepositsPage />} />
              <Route path="money/withdrawals" element={<WithdrawalsPage />} />
              <Route path="money/ids" element={<IdsPage />} />
              <Route path="money/reconcile" element={<ReconcilePage />} />
              <Route path="money/adjustments" element={<AdjustmentsPage />} />
              <Route path="money/settings" element={<SettingsPage />} />
              <Route path="money/audit" element={<AuditPage />} />
              <Route path="*" element={<Navigate to="/admin" replace />} />
            </Routes>
          </StepUpProvider>
        </main>
      </div>
    </AdminSessionContext.Provider>
  )
}

function StaffLogin({ session, onLoggedIn }: { session: AdminSession; onLoggedIn: (s: AdminSession) => void }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [code, setCode] = useState('')
  const [needsCode, setNeedsCode] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      onLoggedIn(await login(username.trim(), password, session.csrfToken, needsCode ? code.trim() : undefined))
    } catch (err) {
      if (err instanceof AdminApiError && err.code === 'CODE_REQUIRED') {
        setNeedsCode(true)
        setError(null)
      } else setError(err instanceof Error ? err.message : 'Something went wrong.')
      setBusy(false)
    }
  }

  return (
    <main className="page stack admin-gate">
      <Logo size={40} />
      <h1>Staff dashboard</h1>
      <p className="muted">Log in with a staff account. Game accounts cannot open the dashboard.</p>
      <form className="stack" onSubmit={submit}>
        <label className="field">
          <span className="field__label">Username</span>
          <input
            className="field__input"
            autoComplete="username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            required
          />
        </label>
        <label className="field">
          <span className="field__label">Password</span>
          <input
            className="field__input"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </label>
        {needsCode && (
          <label className="field">
            <span className="field__label">Code from your authenticator app (or a backup code)</span>
            <input
              className="field__input"
              autoComplete="one-time-code"
              value={code}
              onChange={(e) => setCode(e.target.value)}
              autoFocus
              required
            />
          </label>
        )}
        {error && (
          <p className="field__error" role="alert">
            {error}
          </p>
        )}
        <Button type="submit" block disabled={busy}>
          {busy ? 'Logging in…' : 'Log in'}
        </Button>
      </form>
      <Link to="/" className="back-link">
        ← Back to the game
      </Link>
    </main>
  )
}
