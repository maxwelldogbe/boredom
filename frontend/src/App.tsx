import { lazy, Suspense } from 'react'
import { BrowserRouter, Navigate, Route, Routes, useSearchParams } from 'react-router-dom'
import { AccountSync } from './components/AccountSync'
import { InviteBanners } from './components/Invites'
import { RequireProfile } from './components/RequireProfile'
import { ToastHost } from './components/ToastHost'
import AboutPage from './pages/AboutPage'
import FriendsPage from './pages/FriendsPage'
import HomePage from './pages/HomePage'
import JoinPage from './pages/JoinPage'
import ProfilePage from './pages/ProfilePage'
import RoomPage from './pages/RoomPage'
import SetupPage from './pages/SetupPage'
import { GuestQuotaProvider } from './state/GuestQuotaProvider'
import { RoomProvider } from './state/RoomProvider'
import { SocialProvider } from './state/SocialProvider'

/** /signup: the Create account form on /profile, keeping where to go afterwards. */
function SignupRedirect() {
  const next = useSearchParams()[0].get('next')
  return <Navigate to={next ? `/profile?next=${encodeURIComponent(next)}` : '/profile'} replace />
}

// The staff dashboard is a separate chunk: players never download it.
const AdminApp = lazy(() => import('./admin/AdminApp'))

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<HomePage />} />
      <Route path="/setup" element={<SetupPage />} />
      <Route
        path="/profile"
        element={
          <RequireProfile>
            <ProfilePage />
          </RequireProfile>
        }
      />
      <Route path="/about" element={<AboutPage />} />
      <Route
        path="/signup"
        element={
          <RequireProfile>
            <SignupRedirect />
          </RequireProfile>
        }
      />
      <Route
        path="/friends"
        element={
          <RequireProfile>
            <FriendsPage />
          </RequireProfile>
        }
      />
      <Route
        path="/join/:code"
        element={
          <RequireProfile>
            <JoinPage />
          </RequireProfile>
        }
      />
      <Route
        path="/room/:code"
        element={
          <RequireProfile>
            <RoomPage />
          </RequireProfile>
        }
      />
      <Route
        path="/admin/*"
        element={
          <Suspense fallback={<p className="page muted">Loading…</p>}>
            <AdminApp />
          </Suspense>
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <RoomProvider>
        <SocialProvider>
          <GuestQuotaProvider>
            <AccountSync />
            <InviteBanners />
            <AppRoutes />
            <ToastHost />
          </GuestQuotaProvider>
        </SocialProvider>
      </RoomProvider>
    </BrowserRouter>
  )
}
