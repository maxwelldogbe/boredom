/** Shared client/server constants, read from <repo>/shared/constants.json (never hardcode). */
import raw from '../../../shared/constants.json'

export type SharedConstants = typeof raw

export const C: Readonly<SharedConstants> = raw
