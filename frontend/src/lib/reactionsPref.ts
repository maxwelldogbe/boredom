/** "Hide reactions", remembered per browser (localStorage via the try/catch wrapper). */
import { useSyncExternalStore } from 'react'
import { readItem, writeItem } from './storage'

export const HIDE_REACTIONS_KEY = 'partypack.hideReactions'

const listeners = new Set<() => void>()

export function reactionsHidden(): boolean {
  return readItem(HIDE_REACTIONS_KEY) === '1'
}

export function setReactionsHidden(hidden: boolean): void {
  writeItem(HIDE_REACTIONS_KEY, hidden ? '1' : '0')
  listeners.forEach((listener) => listener())
}

function subscribe(listener: () => void) {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

/** The current setting; re-renders when it changes anywhere in the app. */
export function useReactionsHidden(): boolean {
  return useSyncExternalStore(subscribe, reactionsHidden, reactionsHidden)
}
