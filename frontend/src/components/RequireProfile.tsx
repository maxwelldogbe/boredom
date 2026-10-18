import type { ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { getProfile } from '../lib/profileStore'

/** Sends visitors without a profile to /setup, remembering where they were going. */
export function RequireProfile({ children }: { children: ReactNode }) {
  const location = useLocation()
  if (getProfile()) return <>{children}</>
  const next = `${location.pathname}${location.search}`
  return <Navigate to={`/setup?next=${encodeURIComponent(next)}`} replace />
}

