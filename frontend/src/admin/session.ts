import { createContext, useContext } from 'react'
import type { AdminSession } from './api'

export interface AdminSessionValue {
  session: AdminSession
  /** A request came back 401/403: re-check the session (shows the login screen if needed). */
  onUnauthorized: () => void
}

export const AdminSessionContext = createContext<AdminSessionValue | null>(null)

export function useAdminSession(): AdminSessionValue {
  const value = useContext(AdminSessionContext)
  if (!value) throw new Error('useAdminSession needs <AdminApp>')
  return value
}
