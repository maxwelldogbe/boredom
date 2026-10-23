import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, NavLink, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { Button } from '../components/Button'
import { Logo } from '../components/Logo'
import { AdminApiError, getSession, logout, type AdminSession } from './api'
import ActivityPage from './pages/ActivityPage'
import GameDetailPage from './pages/GameDetailPage'
import GamesPage from './pages/GamesPage'
import LeaderboardsPage from './pages/LeaderboardsPage'
import OverviewPage from './pages/OverviewPage'
import UserDetailPage from './pages/UserDetailPage'
import UsersPage from './pages/UsersPage'
import { AdminSessionContext, type AdminSessionValue } from './session'
import './admin.css'

const NAV = [
  { to: '/admin', label: 'Overview', end: true },
  { to: '/admin/games', label: 'Games' },
  { to: '/admin/users', label: 'Users' },
  { to: '/admin/leaderboards', label: 'Leaderboards' },
  { to: '/admin/activity', label: 'Activity' },
]

/** The staff dashboard (lazy-loaded at /admin/*). Uses the Django admin session. */
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
    () => (session ? { session, onUnauthorized: load } : null),
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
  if (!session.staff) return <StaffLogin session={session} />

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
          </nav>
          <div className="admin__me">
            <span className="muted">{session.username}</span>
            <a href={session.adminUrl}>Django admin</a>
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
          <Routes>
            <Route index element={<OverviewPage />} />
            <Route path="games" element={<GamesPage />} />
            <Route path="games/:gameId" element={<GameDetailPage />} />
            <Route path="users" element={<UsersPage />} />
            <Route path="users/u/:userId" element={<UserDetailPage kind="registered" />} />
            <Route path="users/g/:guestKey" element={<UserDetailPage kind="guest" />} />
            <Route path="leaderboards" element={<LeaderboardsPage />} />
            <Route path="activity" element={<ActivityPage />} />
            <Route path="*" element={<Navigate to="/admin" replace />} />
          </Routes>
        </main>
      </div>
    </AdminSessionContext.Provider>
  )
}

function StaffLogin({ session }: { session: AdminSession }) {
  const location = useLocation()
  const next = `${location.pathname}${location.search}`
  return (
    <main className="page stack admin-gate">
      <Logo size={40} />
      <h1>Staff dashboard</h1>
      <p className="muted">
        Log in with a staff account. Game accounts cannot open the dashboard.
      </p>
      <a className="btn btn--primary btn--block" href={`${session.loginUrl}?next=${encodeURIComponent(next)}`}>
        Log in as staff
      </a>
      <Link to="/" className="back-link">
        ← Back to the game
      </Link>
    </main>
  )
}
