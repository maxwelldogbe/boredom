/** "Verify your age": ID type, name, number, date of birth and photos, uploaded with progress. */
import { useId, useState, type FormEvent } from 'react'
import { Button } from '../../../components/Button'
import { TextInput } from '../../../components/TextInput'
import { C } from '../../../lib/constants'
import { ID_TYPE_LABELS, NemesisError, idFileError, nemesisMessage, uploadId, type NemesisStatus } from '../../../lib/nemesis'
import { BackButton, FormError } from './shared'

function FileField({ label, error, onChange }: { label: string; error: string | null; onChange: (file: File | null) => void }) {
  const id = useId()
  return (
    <div className="field">
      <label htmlFor={id} className="field__label">
        {label}
      </label>
      <input
        id={id}
        type="file"
        accept="image/jpeg,image/png"
        className="field__input"
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? `${id}-error` : undefined}
        onChange={(e) => onChange(e.target.files?.[0] ?? null)}
      />
      {error && (
        <p id={`${id}-error`} className="field__error" role="alert">
          {error}
        </p>
      )}
    </div>
  )
}

export function IdForm({ retentionDays, onDone, onBack }: { retentionDays: number; onDone: (status: NemesisStatus) => void; onBack: () => void }) {
  const typeId = useId()
  const [idType, setIdType] = useState<string>(C.ID_TYPES[0])
  const [fullName, setFullName] = useState('')
  const [idNumber, setIdNumber] = useState('')
  const [dob, setDob] = useState('')
  const [front, setFront] = useState<File | null>(null)
  const [back, setBack] = useState<File | null>(null)
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [formError, setFormError] = useState<string | null>(null)
  const [progress, setProgress] = useState<number | null>(null)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    const found: Record<string, string> = {}
    if (fullName.trim().length < 2) found.fullName = 'Enter your name as it appears on the ID.'
    if (idNumber.trim().length < 4) found.idNumber = 'Enter the ID number.'
    if (!dob) found.dob = 'Enter your date of birth.'
    const frontError = idFileError(front, true)
    const backError = idFileError(back, false)
    if (frontError) found.front = frontError
    if (backError) found.back = backError
    setErrors(found)
    setFormError(null)
    if (Object.keys(found).length) return
    const form = new FormData()
    form.append('idType', idType)
    form.append('fullName', fullName.trim())
    form.append('idNumber', idNumber.trim())
    form.append('dob', dob)
    form.append('front', front as File)
    if (back) form.append('back', back)
    setProgress(0)
    try {
      onDone(await uploadId(form, setProgress))
    } catch (err) {
      setProgress(null)
      if (err instanceof NemesisError && Object.keys(err.fields).length) setErrors(err.fields)
      setFormError(nemesisMessage(err))
    }
  }

  const busy = progress !== null
  return (
    <form className="stack" onSubmit={submit} noValidate>
      <BackButton onBack={onBack} />
      <h3>Verify your age</h3>
      <p className="muted">
        Used only to confirm you are 18 or older. Images are stored privately and deleted {retentionDays} days after
        review.
      </p>
      <div className="field">
        <label htmlFor={typeId} className="field__label">
          ID type
        </label>
        <select id={typeId} className="field__input" value={idType} onChange={(e) => setIdType(e.target.value)}>
          {C.ID_TYPES.map((t) => (
            <option key={t} value={t}>
              {ID_TYPE_LABELS[t] ?? t}
            </option>
          ))}
        </select>
      </div>
      <TextInput label="Full name (as on the ID)" autoComplete="name" value={fullName} onChange={(e) => setFullName(e.target.value)} error={errors.fullName} />
      <TextInput label="ID number" autoComplete="off" value={idNumber} onChange={(e) => setIdNumber(e.target.value)} error={errors.idNumber} />
      <TextInput label="Date of birth" type="date" value={dob} onChange={(e) => setDob(e.target.value)} error={errors.dob} />
      <FileField label="Front photo" error={errors.front ?? null} onChange={setFront} />
      <FileField label="Back photo (optional)" error={errors.back ?? null} onChange={setBack} />
      {busy && (
        <div className="stack">
          <progress max={1} value={progress} aria-label="Upload progress" className="nemesis__progress" />
        </div>
      )}
      <FormError message={formError} />
      <Button type="submit" block disabled={busy}>
        {busy ? 'Uploading…' : 'Send for review'}
      </Button>
    </form>
  )
}
