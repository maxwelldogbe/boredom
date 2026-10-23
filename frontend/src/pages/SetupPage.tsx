import { useNavigate, useSearchParams } from 'react-router-dom'
import { createProfile, saveProfile } from '../lib/profileStore'
import { safeNext } from '../lib/navigation'
import { ProfileForm } from './ProfileForm'

/** First visit: pick a nickname and a color, then continue to where you were going. */
export default function SetupPage() {
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const next = safeNext(params.get('next'))
  return (
    <main className="page">
      <h1>Who are you?</h1>
      <p className="muted">Friends will see this name and avatar. No account needed.</p>
      <ProfileForm
        submitLabel="Continue"
        onSubmit={(fields) => {
          saveProfile(createProfile(fields))
          navigate(next, { replace: true })
        }}
      />
    </main>
  )
}
