import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { Button } from '../components/Button'
import { createProfile, saveProfile } from '../lib/profileStore'
import { safeNext } from '../lib/navigation'
import { useRoomActions } from '../state/context'
import { AccountForms } from './AccountForms'
import { ProfileForm } from './ProfileForm'

/** First visit: pick a nickname and a color (or log in), then continue to where you were going. */
export default function SetupPage() {
  const navigate = useNavigate()
  const { toast } = useRoomActions()
  const [params] = useSearchParams()
  const next = safeNext(params.get('next'))
  const [loggingIn, setLoggingIn] = useState(params.get('mode') === 'login')

  if (loggingIn) {
    return (
      <main className="page stack">
        <h1>Log in</h1>
        <p className="muted">Use your saved profile on this device.</p>
        <AccountForms
          allowSignup={false}
          onSignedIn={(profile) => {
            toast(`Welcome back, ${profile.nickname}!`)
            navigate(next, { replace: true })
          }}
        />
        <Button variant="ghost" block onClick={() => setLoggingIn(false)}>
          Play as a guest instead
        </Button>
      </main>
    )
  }

  return (
    <main className="page stack">
      <h1>Who are you?</h1>
      <p className="muted">Friends will see this name and avatar. No account needed.</p>
      <ProfileForm
        submitLabel="Continue"
        onSubmit={(fields) => {
          saveProfile(createProfile(fields))
          navigate(next, { replace: true })
        }}
      />
      <Button variant="ghost" block onClick={() => setLoggingIn(true)}>
        I already have an account
      </Button>
    </main>
  )
}
