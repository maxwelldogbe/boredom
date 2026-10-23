import { useEffect } from 'react'
import { AccountError, adoptSession, fetchMe, forgetAccount, getAuthToken } from '../lib/account'
import { getProfile } from '../lib/profileStore'
import { useRoomActions } from '../state/context'

export const LOGIN_EXPIRED_MESSAGE = 'Your login has expired. Log in again from your profile.'

/** On start-up, refresh a logged-in profile from the server, or forget an expired login. */
export function AccountSync() {
  const { toast } = useRoomActions()
  useEffect(() => {
    const token = getAuthToken()
    if (!token || getProfile()?.type !== 'registered') return
    fetchMe(token)
      .then(adoptSession)
      .catch((err: unknown) => {
        if (err instanceof AccountError && err.code === 'UNAUTHORIZED') {
          forgetAccount()
          toast(LOGIN_EXPIRED_MESSAGE, 'error')
        }
        // Network trouble: keep the login and try again next time.
      })
  }, [toast])
  return null
}
