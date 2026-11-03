import { useState } from 'react'
import { AdminApiError } from '../api'
import { useAdminSession } from '../session'
import { useStepUp } from './stepUpContext'

/** Run a staff money action through step-up; keeps busy and error state, refreshes badges. */
export function useMoneyAction() {
  const { run } = useStepUp()
  const { refresh } = useAdminSession()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [fields, setFields] = useState<Record<string, string>>({})

  const act = async <T,>(action: () => Promise<T>): Promise<T | null> => {
    setBusy(true)
    setError(null)
    setFields({})
    try {
      const result = await run(action)
      refresh()
      return result
    } catch (err) {
      if (err instanceof AdminApiError) {
        setError(err.message)
        setFields(err.fields)
      } else setError('Something went wrong.')
      return null
    } finally {
      setBusy(false)
    }
  }
  return { act, busy, error, fields, setError }
}
