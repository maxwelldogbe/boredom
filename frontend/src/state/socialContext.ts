import { createContext, useContext } from 'react'
import type { FriendsOverview } from '../lib/social'
import type { FriendStatus, InvitePush, PlayerCard, PresenceMode } from '../types/protocol'

export type OverviewLoad =
  | { status: 'idle' } // a guest, or not loaded yet
  | { status: 'loading' }
  | { status: 'ready'; data: FriendsOverview }
  | { status: 'error'; message: string }

/** An invite shown as a banner. */
export interface ReceivedInvite extends InvitePush {
  /** When it runs out on this device's clock (expiresAt corrected by the server clock offset). */
  localExpiresAt: number
}

export interface Social {
  /** A registered profile with a token on this device. */
  signedIn: boolean
  overview: OverviewLoad
  /** Incoming friend requests, for the home badge (0 while unknown). */
  incomingCount: number
  /** The account's presence setting, once known. */
  presence: PresenceMode | null
  refresh(): void
  /** Change the loaded overview locally after a successful action. */
  update(change: (data: FriendsOverview) => FriendsOverview): void
  setPresence(mode: PresenceMode): void
  /** Pending invites to this account, newest first. */
  invites: ReceivedInvite[]
  /** When each friend (by tag) was last invited from this device, for "Sent". */
  sentAt: Record<string, number>
  /** A friend's live status, or null if they are not a friend (or the list is not loaded). */
  statusOf(tag: string): FriendStatus | null
  /** invite:send from the current lobby. */
  sendInvite(friend: PlayerCard): Promise<void>
  /** invite:accept; resolves with the room code. The banner goes away either way. */
  acceptInvite(inviteId: string): Promise<string>
  declineInvite(inviteId: string): void
}

export const SocialContext = createContext<Social | null>(null)

export function useSocial(): Social {
  const value = useContext(SocialContext)
  if (!value) throw new Error('useSocial must be used inside <SocialProvider>')
  return value
}
