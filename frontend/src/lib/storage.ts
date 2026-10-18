/**
 * localStorage wrapped in try/catch, falling back to memory when storage is unavailable
 * (private mode, blocked site data, quota errors).
 */
const memory = new Map<string, string>()

function store(): Storage | null {
  try {
    return typeof window !== 'undefined' ? window.localStorage : null
  } catch {
    return null
  }
}

export function readItem(key: string): string | null {
  try {
    const value = store()?.getItem(key)
    if (value !== null && value !== undefined) return value
  } catch {
    // fall through to memory
  }
  return memory.get(key) ?? null
}

export function writeItem(key: string, value: string): void {
  memory.set(key, value)
  try {
    store()?.setItem(key, value)
  } catch {
    // memory copy is kept
  }
}

export function removeItem(key: string): void {
  memory.delete(key)
  try {
    store()?.removeItem(key)
  } catch {
    // ignore
  }
}

/** Test helper: forget the in-memory fallback. */
export function clearMemoryStorage(): void {
  memory.clear()
}
