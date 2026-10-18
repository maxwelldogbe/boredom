/** A same-site path to return to after setup, or "/" if `next` is missing or unsafe. */
export function safeNext(next: string | null): string {
  return next && next.startsWith('/') && !next.startsWith('//') ? next : '/'
}
