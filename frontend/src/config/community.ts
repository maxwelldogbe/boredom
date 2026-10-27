/** Our WhatsApp channel. Every "Join our WhatsApp community" button hides itself when this is
 *  empty, still a placeholder, or not an https:// link. */
export const WHATSAPP_CHANNEL_URL = 'https://whatsapp.com/channel/0029VbDd9Q3CsU9ToglISe42'

const PLACEHOLDER = /placeholder|your[-_ ]?(channel|link)|example|xxx|todo/i

/** The link to show, or null if `url` is not a usable https:// address. */
export function communityUrl(url: string = WHATSAPP_CHANNEL_URL): string | null {
  const value = url.trim()
  if (!value.startsWith('https://') || PLACEHOLDER.test(value)) return null
  try {
    return new URL(value).hostname ? value : null
  } catch {
    return null
  }
}
