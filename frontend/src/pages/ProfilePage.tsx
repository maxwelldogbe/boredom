import { useState, type ChangeEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Button } from '../components/Button'
import { Modal } from '../components/Modal'
import {
  exportProfile,
  getProfile,
  importProfile,
  resetProfile,
  saveProfile,
  type Profile,
} from '../lib/profileStore'
import { useRoomActions } from '../state/context'
import { ProfileForm } from './ProfileForm'

/** Edit, export, import or reset the guest profile. (Accounts are out of scope.) */
export default function ProfilePage() {
  const navigate = useNavigate()
  const { toast } = useRoomActions()
  const [profile, setProfile] = useState<Profile | null>(() => getProfile())
  const [formKey, setFormKey] = useState(0)
  const [importError, setImportError] = useState<string | null>(null)
  const [confirmReset, setConfirmReset] = useState(false)

  if (!profile) return null // RequireProfile guards this route

  const onImport = async (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    const result = importProfile(await file.text())
    if (!result.ok) {
      setImportError(result.error)
      return
    }
    saveProfile(result.profile)
    setProfile(result.profile)
    setFormKey((k) => k + 1)
    setImportError(null)
    toast('Profile imported.')
  }

  return (
    <main className="page stack">
      <Link to="/" className="back-link">
        ← Home
      </Link>
      <h1>Your profile</h1>
      <ProfileForm
        key={formKey}
        initial={profile}
        submitLabel="Save changes"
        onSubmit={(fields) => {
          const updated = { ...profile, ...fields }
          saveProfile(updated)
          setProfile(updated)
          toast('Profile saved.')
        }}
      />
      <section className="stack">
        <h2>Backup</h2>
        <Button variant="secondary" block onClick={() => exportProfile(profile)}>
          Export profile
        </Button>
        <label className="btn btn--secondary btn--block">
          Import profile
          <input type="file" accept="application/json,.json" className="visually-hidden" onChange={onImport} />
        </label>
        {importError && (
          <p className="field__error" role="alert">
            {importError}
          </p>
        )}
      </section>
      <Button variant="danger" block onClick={() => setConfirmReset(true)}>
        Reset profile
      </Button>
      {confirmReset && (
        <Modal
          title="Reset your profile?"
          onClose={() => setConfirmReset(false)}
          actions={
            <>
              <Button
                variant="danger"
                block
                onClick={() => {
                  resetProfile()
                  navigate('/setup', { replace: true })
                }}
              >
                Reset
              </Button>
              <Button variant="secondary" block onClick={() => setConfirmReset(false)}>
                Cancel
              </Button>
            </>
          }
        >
          <p>Your nickname, avatar and stats on this device will be deleted.</p>
        </Modal>
      )}
    </main>
  )
}
