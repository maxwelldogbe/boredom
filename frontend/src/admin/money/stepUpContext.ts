import { createContext, useContext } from 'react'

export interface StepUp {
  /** Run a money action; on STEP_UP_REQUIRED ask for a code, then retry it once. */
  run: <T>(action: () => Promise<T>) => Promise<T>
}

export const StepUpContext = createContext<StepUp | null>(null)

export function useStepUp(): StepUp {
  const value = useContext(StepUpContext)
  if (!value) throw new Error('useStepUp needs <StepUpProvider>')
  return value
}
