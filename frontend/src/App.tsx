import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { RequireProfile } from './components/RequireProfile'
import { ToastHost } from './components/ToastHost'
import HomePage from './pages/HomePage'
import JoinPage from './pages/JoinPage'
import ProfilePage from './pages/ProfilePage'
import RoomPage from './pages/RoomPage'
import SetupPage from './pages/SetupPage'
import { RoomProvider } from './state/RoomProvider'

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
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <RoomProvider>
        <AppRoutes />
        <ToastHost />
      </RoomProvider>
    </BrowserRouter>
  )
}
