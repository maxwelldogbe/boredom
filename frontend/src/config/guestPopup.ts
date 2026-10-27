/** How often guests see the signup popup on the final results screen. */
export const FIRST_AFTER_GAMES = 2
export const EVERY_GAMES = 3
export const MIN_MINUTES_BETWEEN = 10
export const BACKOFF_AFTER_DISMISSALS = 3
export const BACKOFF_EVERY_GAMES = 6

/** Seconds after the results show, so the player sees their result first. */
export const SHOW_DELAY_MS = 1500

export const STORAGE_KEY = 'partypack.guestPopup'

/** The flyer at the top of the popup and the lock wall (frontend/public). While `src` is null
 *  they are text-only. `alt` describes what the image shows. */
export const FLYER: { src: string | null; alt: string } = {
  src: encodeURI('/Guest popup@1x.png'),
  alt: 'Guest mode: keep the fun going. What you are missing as a guest: unlimited games, friends by tag name, stats and profile, and custom avatars.',
}
