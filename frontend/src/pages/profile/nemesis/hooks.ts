/** Hooks and labels shared by the Nemesis screens. */
import { useCallback, useEffect, useState } from 'react'
import { formatMoney, nemesisMessage, type Wallet } from '../../../lib/nemesis'
import type { Load } from '../useLoad'

/** Fetch on mount and on retry(); errors become plain messages. */
export function useNemesisLoad<T>(fetcher: () => Promise<T>): [Load<T>, () => void, (data: T) => void] {
  const [state, setState] = useState<Load<T>>({ status: 'loading' })
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    let live = true
    Promise.resolve()
      .then(fetcher)
      .then((data) => live && setState({ status: 'ready', data }))
      .catch((err: unknown) => live && setState({ status: 'error', message: nemesisMessage(err) }))
    return () => {
      live = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- once per attempt
  }, [attempt])
  const retry = useCallback(() => {
    setState({ status: 'loading' })
    setAttempt((n) => n + 1)
  }, [])
  const set = useCallback((data: T) => setState({ status: 'ready', data }), [])
  return [state, retry, set]
}

export function useMoney(wallet: Pick<Wallet, 'currency' | 'minorUnit'>) {
  return (amount: number) => formatMoney(amount, wallet.currency, wallet.minorUnit)
}

export const WITHDRAWAL_STATUS: Record<string, string> = {
  pending_review: 'Waiting for review',
  approved: 'Approved, being paid',
  paid: 'Paid',
  rejected: 'Not approved',
  cancelled: 'Cancelled',
}
