import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { getAuthToken, onAuthChange } from '../lib/account'
import { getProfile } from '../lib/profileStore'
import { fetchFriends, socialError, type FriendsOverview } from '../lib/social'
import { C } from '../lib/constants'
import type { Avatar, FriendStatus, PlayerCard, PresenceMode } from '../types/protocol'
import { useRoomActions, useRoomState } from './context'
import { SocialContext, type OverviewLoad, type ReceivedInvite, type Social } from './socialContext'

function isSignedIn(): boolean {
  return getProfile()?.type === 'registered' && Boolean(getAuthToken())
}

const avatarKey = (avatar: Avatar) => `${avatar.style}/${avatar.seed}`

function withStatuses(data: FriendsOverview, statuses: Record<string, FriendStatus>): FriendsOverview {
  return { ...data, friends: data.friends.map((f) => ({ ...f, status: statuses[f.tag] ?? f.status })) }
}

/** Friends, presence and invites for a signed-in account: sends auth:hello after every
 *  (re)connect and login, loads the friends overview, and keeps it live from the friends:* and
 *  invite:* pushes. */
export function SocialProvider({ children }: { children: ReactNode }) {
  const { socket, toast } = useRoomActions()
  const { room } = useRoomState()
  const [signedIn, setSignedIn] = useState(isSignedIn)
  const [overview, setOverview] = useState<OverviewLoad>(() => (isSignedIn() ? { status: 'loading' } : { status: 'idle' }))
  const [presence, setPresenceState] = useState<PresenceMode | null>(null)
  const [invites, setInvites] = useState<ReceivedInvite[]>([])
  const [sentAt, setSentAt] = useState<Record<string, number>>({})
  const statuses = useRef<Record<string, FriendStatus>>({})
  const overviewRef = useRef(overview)
  const loadId = useRef(0)
  // Friends invited from this device, by the avatar their seat will carry (an account keeps
  // its avatar in every room), until the invite would have run out.
  const awaiting = useRef(new Map<string, number>())
  const seen = useRef<{ code: string | null; ids: Set<string> }>({ code: null, ids: new Set() })

  useEffect(() => {
    overviewRef.current = overview
  }, [overview])

  /** Fetch the overview; state changes only when the answer arrives. */
  const load = useCallback(() => {
    const id = ++loadId.current
    fetchFriends()
      .then((data) => id === loadId.current && setOverview({ status: 'ready', data: withStatuses(data, statuses.current) }))
      .catch((err: unknown) => id === loadId.current && setOverview({ status: 'error', message: socialError(err) }))
  }, [])

  const refresh = useCallback(() => {
    if (!isSignedIn()) {
      loadId.current++
      setOverview({ status: 'idle' })
      return
    }
    setOverview((current) => (current.status === 'ready' ? current : { status: 'loading' }))
    load()
  }, [load])

  const update = useCallback((change: (data: FriendsOverview) => FriendsOverview) => {
    setOverview((current) => (current.status === 'ready' ? { status: 'ready', data: change(current.data) } : current))
  }, [])

  const hello = useCallback(() => {
    const token = isSignedIn() ? getAuthToken() : null
    socket
      .request('auth:hello', token ? { authToken: token } : {})
      .then((data) => {
        setPresenceState(data.presence)
        // Pushes only reach a bound connection: reload once bound, so anything that changed
        // between the first load (or a disconnect) and now is not missed.
        if (token) load()
      })
      .catch(() => {}) // a guest, or an expired login (AccountSync deals with that)
  }, [socket, load])

  const dropInvite = useCallback((inviteId: string) => {
    setInvites((list) => list.filter((i) => i.inviteId !== inviteId))
  }, [])

  useEffect(() => {
    const setStatus = (tag: string, status: FriendStatus) => {
      statuses.current[tag] = status
      update((data) => withStatuses(data, { [tag]: status }))
    }
    const offConnect = socket.onConnect(() => {
      if (isSignedIn()) hello()
    })
    const offAuth = onAuthChange(() => {
      const now = isSignedIn()
      setSignedIn(now)
      statuses.current = {}
      setPresenceState(null)
      setInvites([])
      setSentAt({})
      awaiting.current.clear()
      if (socket.status === 'connected') hello()
      refresh()
    })
    const offPush = socket.onPush((msg) => {
      switch (msg.type) {
        case 'friends:snapshot':
          statuses.current = Object.fromEntries(msg.data.friends.map((f) => [f.tag, f.status]))
          update((data) => withStatuses(data, statuses.current))
          break
        case 'friends:presence':
          setStatus(msg.data.tag, msg.data.status)
          break
        case 'friends:request': {
          const request = msg.data.request
          update((data) =>
            data.incoming.some((r) => r.requestId === request.requestId)
              ? data
              : { ...data, incoming: [request, ...data.incoming] },
          )
          break
        }
        case 'friends:accepted':
          refresh()
          break
        case 'friends:removed':
          delete statuses.current[msg.data.tag]
          update((data) => ({ ...data, friends: data.friends.filter((f) => f.tag !== msg.data.tag) }))
          break
        case 'invite:received': {
          if (!isSignedIn()) break
          const invite = msg.data
          const localExpiresAt = invite.expiresAt - invite.serverNow + Date.now()
          setInvites((list) => [{ ...invite, localExpiresAt }, ...list.filter((i) => i.inviteId !== invite.inviteId)])
          break
        }
        case 'invite:expired':
        case 'invite:cleared':
          dropInvite(msg.data.inviteId)
          break
      }
    })
    if (socket.status === 'connected' && isSignedIn()) hello()
    return () => {
      offConnect()
      offAuth()
      offPush()
    }
  }, [socket, hello, refresh, update, dropInvite])

  // "{nickname} joined": a new registered seat wearing an invited friend's avatar.
  useEffect(() => {
    const code = room?.code ?? null
    const ids = new Set(room?.players.map((p) => p.id) ?? [])
    const before = seen.current
    seen.current = { code, ids }
    if (!room || code !== before.code) return
    const now = Date.now()
    for (const p of room.players) {
      if (before.ids.has(p.id) || p.type !== 'registered') continue
      const key = avatarKey(p.avatar)
      const until = awaiting.current.get(key)
      if (until === undefined) continue
      awaiting.current.delete(key)
      if (until > now) toast(`${p.nickname} joined`)
    }
  }, [room, toast])

  useEffect(() => {
    if (signedIn) load()
  }, [signedIn, load])

  const value = useMemo<Social>(
    () => ({
      signedIn,
      overview,
      incomingCount: overview.status === 'ready' ? overview.data.incoming.length : 0,
      presence,
      refresh,
      update,
      setPresence: setPresenceState,
      invites,
      sentAt,
      statusOf(tag) {
        const current = overviewRef.current
        if (current.status !== 'ready') return null
        const friend = current.data.friends.find((f) => f.tag === tag)
        return friend ? (statuses.current[tag] ?? friend.status) : null
      },
      async sendInvite(friend: PlayerCard) {
        await socket.request('invite:send', { tag: friend.tag })
        const now = Date.now()
        setSentAt((all) => ({ ...all, [friend.tag]: now }))
        awaiting.current.set(avatarKey(friend.avatar), now + C.INVITE_TTL_MS)
      },
      async acceptInvite(inviteId) {
        try {
          return (await socket.request('invite:accept', { inviteId })).code
        } finally {
          dropInvite(inviteId)
        }
      },
      declineInvite(inviteId) {
        dropInvite(inviteId)
        socket.request('invite:decline', { inviteId }).catch(() => {}) // always ok; never told to the sender
      },
    }),
    [signedIn, overview, presence, refresh, update, invites, sentAt, socket, dropInvite],
  )
  return <SocialContext.Provider value={value}>{children}</SocialContext.Provider>
}
