/** Runs `task`, calling setSlow(true) if it takes longer than `afterMs` (server waking up). */
export async function withSlowNotice<T>(
  task: () => Promise<T>,
  setSlow: (slow: boolean) => void,
  afterMs = 3000,
): Promise<T> {
  const timer = setTimeout(() => setSlow(true), afterMs)
  try {
    return await task()
  } finally {
    clearTimeout(timer)
    setSlow(false)
  }
}

export const SLOW_SERVER_MESSAGE = 'Waking up the server, this can take up to a minute.'
