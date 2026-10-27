/** /friends: the presence setting, add a friend by tag, and the Friends, Requests and Blocked
 *  tabs. Registered players only; guests get a card inviting them to create an account. */
import { useEffect, useId, useState, type FormEvent, type KeyboardEvent, type ReactNode } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { Button } from '../components/Button'
import { EmptyState, Loading } from '../components/EmptyState'
import { InviteToPlayButton } from '../components/Invites'
import { Menu } from '../components/Menu'
import { Modal } from '../components/Modal'
import { PlayerDialogs, type PlayerDialogKind } from '../components/PlayerDialogs'
import { StatusLabel } from '../components/StatusLabel'
import { monthYear } from '../lib/format'
import {
  acceptRequest,
  cancelRequest,
  cleanTagInput,
  declineRequest,
  fetchFriendProfile,
  fetchSettings,
  friendRequestError,
  PRESENCE_OPTIONS,
  savePresence,
  sendFriendRequest,
  socialError,
  STATUS_ORDER,
  unblockPlayer,
  type Friend,
  type FriendProfile,
  type FriendsOverview,
} from '../lib/social'
import { C } from '../lib/constants'
import { useRoomActions } from '../state/context'
import { useSocial } from '../state/socialContext'
import type { FriendRequestEntry, PlayerCard } from '../types/protocol'
import { ByGameSection, LoadError, RingAvatar, StatsSection } from './profile/ProfileSections'
import type { Load } from './profile/useLoad'

type Tab = 'friends' | 'requests' | 'blocked'
const TABS: Tab[] = ['friends', 'requests', 'blocked']

export default function FriendsPage() {
  const social = useSocial()
  return (
    <main className="page stack friends">
      <Link to="/" className="back-link">
        ← Home
      </Link>
      <h1>Friends</h1>
      {social.signedIn ? <SignedInFriends /> : <GuestCard />}
    </main>
  )
}

function GuestCard() {
  const navigate = useNavigate()
  return (
    <section className="card stack" aria-labelledby="friends-guest">
      <h2 id="friends-guest">Create an account to add friends</h2>
      <p className="muted">
        With a free account you can add friends by their tag, see when they are online and invite them to your room.
      </p>
      <Button block onClick={() => navigate('/profile')}>
        Create account
      </Button>
      <Button variant="secondary" block onClick={() => navigate('/profile?mode=login')}>
        Sign in
      </Button>
    </section>
  )
}

function SignedInFriends() {
  const social = useSocial()
  const [params, setParams] = useSearchParams()
  const wanted = params.get('tab') as Tab | null
  const tab: Tab = wanted && TABS.includes(wanted) ? wanted : 'friends'
  const tabsId = useId()
  const setTab = (next: Tab) => setParams(next === 'friends' ? {} : { tab: next }, { replace: true })

  const onTabKey = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return
    e.preventDefault()
    const next = TABS[(TABS.indexOf(tab) + (e.key === 'ArrowRight' ? 1 : -1) + TABS.length) % TABS.length]
    setTab(next)
    document.getElementById(`${tabsId}-${next}`)?.focus()
  }

  const overview = social.overview
  const counts =
    overview.status === 'ready'
      ? { friends: overview.data.friends.length, requests: overview.data.incoming.length, blocked: overview.data.blocked.length }
      : null
  const labels: Record<Tab, string> = { friends: 'Friends', requests: 'Requests', blocked: 'Blocked' }

  return (
    <>
      <PresenceControl />
      <AddFriend />
      <div className="tabs" role="tablist" aria-label="Friends lists" onKeyDown={onTabKey}>
        {TABS.map((t) => (
          <button
            key={t}
            type="button"
            role="tab"
            id={`${tabsId}-${t}`}
            className="tabs__tab"
            aria-selected={tab === t}
            aria-controls={`${tabsId}-panel`}
            tabIndex={tab === t ? 0 : -1}
            onClick={() => setTab(t)}
          >
            {labels[t]}
            {t === 'requests' && counts && counts.requests > 0 && (
              <span className="count-badge" aria-label={`${counts.requests} waiting`}>
                {counts.requests}
              </span>
            )}
          </button>
        ))}
      </div>
      <div id={`${tabsId}-panel`} role="tabpanel" aria-labelledby={`${tabsId}-${tab}`} className="stack">
        {overview.status === 'loading' || overview.status === 'idle' ? (
          <Loading label="Loading your friends…" />
        ) : overview.status === 'error' ? (
          <LoadError message={overview.message} onRetry={social.refresh} />
        ) : tab === 'friends' ? (
          <FriendsTab data={overview.data} />
        ) : tab === 'requests' ? (
          <RequestsTab data={overview.data} />
        ) : (
          <BlockedTab data={overview.data} />
        )}
      </div>
    </>
  )
}

// ----- presence setting --------------------------------------------------------------

function PresenceControl() {
  const social = useSocial()
  const { toast } = useRoomActions()
  const [saving, setSaving] = useState(false)
  const { presence, setPresence } = social

  useEffect(() => {
    if (presence !== null) return
    let live = true
    fetchSettings()
      .then((s) => live && setPresence(s.presence))
      .catch(() => {})
    return () => {
      live = false
    }
  }, [presence, setPresence])

  return (
    <fieldset className="presence" disabled={saving || presence === null}>
      <legend className="presence__legend">Your status</legend>
      <div className="presence__options" role="radiogroup" aria-label="Your status">
        {PRESENCE_OPTIONS.map((o) => (
          <button
            key={o.value}
            type="button"
            role="radio"
            aria-checked={presence === o.value}
            className="presence__option"
            onClick={async () => {
              if (presence === o.value) return
              const previous = presence
              setPresence(o.value)
              setSaving(true)
              try {
                setPresence((await savePresence(o.value)).presence)
              } catch (err) {
                if (previous) setPresence(previous)
                toast(socialError(err), 'error')
              } finally {
                setSaving(false)
              }
            }}
          >
            <span className="presence__label">{o.label}</span>
            <span className="presence__hint">{o.hint}</span>
          </button>
        ))}
      </div>
    </fieldset>
  )
}

// ----- add friend --------------------------------------------------------------------

function AddFriend() {
  const social = useSocial()
  const { toast } = useRoomActions()
  const [value, setValue] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const inputId = useId()
  const errorId = useId()

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (value.length !== C.TAG_LENGTH) {
      setError(`A tag is ${C.TAG_LENGTH} letters and numbers, like #K7M2QX.`)
      return
    }
    setBusy(true)
    setError(null)
    try {
      const result = await sendFriendRequest(value)
      toast(result.status === 'friends' ? "You're now friends!" : 'Request sent')
      setValue('')
      social.refresh()
    } catch (err) {
      setError(friendRequestError(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="add-friend" onSubmit={submit} noValidate>
      <label className="field__label" htmlFor={inputId}>
        Add a friend by tag
      </label>
      <div className="add-friend__row">
        <span className="add-friend__hash" aria-hidden="true">
          #
        </span>
        <input
          id={inputId}
          className="field__input add-friend__input"
          value={value}
          placeholder="K7M2QX"
          autoCapitalize="characters"
          autoComplete="off"
          spellCheck={false}
          inputMode="text"
          aria-invalid={Boolean(error)}
          aria-describedby={error ? errorId : undefined}
          onChange={(e) => {
            setValue(cleanTagInput(e.target.value))
            setError(null)
          }}
          disabled={busy}
        />
        <Button type="submit" disabled={busy || value.length === 0}>
          {busy ? 'Sending…' : 'Send'}
        </Button>
      </div>
      {error && (
        <p id={errorId} className="field__error" role="alert">
          {error}
        </p>
      )}
    </form>
  )
}

// ----- friends tab -------------------------------------------------------------------

function PlayerRow({ player, children }: { player: PlayerCard; children?: ReactNode }) {
  return (
    <li className="friend-row">
      <RingAvatar avatar={player.avatar} nickname={player.nickname} color={player.color} size={44} />
      <span className="friend-row__who">
        <span className="friend-row__name">{player.nickname}</span>
        <span className="muted friend-row__tag">#{player.tag}</span>
      </span>
      <span className="friend-row__end">{children}</span>
    </li>
  )
}

type Dialog = { kind: 'profile' | PlayerDialogKind; friend: PlayerCard } | null

const sortFriends = (friends: Friend[]) =>
  [...friends].sort(
    (a, b) =>
      STATUS_ORDER.indexOf(a.status) - STATUS_ORDER.indexOf(b.status) ||
      a.nickname.localeCompare(b.nickname) ||
      a.tag.localeCompare(b.tag),
  )

function FriendsTab({ data }: { data: FriendsOverview }) {
  const [dialog, setDialog] = useState<Dialog>(null)
  if (data.friends.length === 0) {
    return (
      <EmptyState icon="👋" title="No friends yet">
        Ask a friend for their tag (it's on their profile) and add it above.
      </EmptyState>
    )
  }
  return (
    <>
      <ul className="friend-list">
        {sortFriends(data.friends).map((f) => (
          <PlayerRow key={f.tag} player={f}>
            <StatusLabel status={f.status} />
            {f.status === 'online' && <InviteToPlayButton friend={f} />}
            <Menu
              label={`More for ${f.nickname}`}
              items={[
                { label: 'View profile', onSelect: () => setDialog({ kind: 'profile', friend: f }) },
                { label: 'Remove friend', onSelect: () => setDialog({ kind: 'remove', friend: f }) },
                { label: 'Block', onSelect: () => setDialog({ kind: 'block', friend: f }), danger: true },
                { label: 'Report', onSelect: () => setDialog({ kind: 'report', friend: f }), danger: true },
              ]}
            />
          </PlayerRow>
        ))}
      </ul>
      {dialog?.kind === 'profile' ? (
        <FriendProfileModal friend={dialog.friend} onClose={() => setDialog(null)} />
      ) : (
        <PlayerDialogs dialog={dialog} onClose={() => setDialog(null)} />
      )}
    </>
  )
}

function FriendProfileModal({ friend, onClose }: { friend: PlayerCard; onClose: () => void }) {
  const [state, setState] = useState<Load<FriendProfile>>({ status: 'loading' })
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    let live = true
    fetchFriendProfile(friend.tag)
      .then((data) => live && setState({ status: 'ready', data }))
      .catch((err: unknown) => live && setState({ status: 'error', message: socialError(err) }))
    return () => {
      live = false
    }
  }, [friend.tag, attempt])
  const retry = () => {
    setState({ status: 'loading' })
    setAttempt((n) => n + 1)
  }
  const stats: Load<FriendProfile['stats']> = state.status === 'ready' ? { status: 'ready', data: state.data.stats } : state
  return (
    <Modal
      title={friend.nickname}
      onClose={onClose}
      actions={
        <Button variant="secondary" block onClick={onClose}>
          Close
        </Button>
      }
    >
      <div className="friend-profile stack">
        <div className="friend-profile__head">
          <RingAvatar avatar={friend.avatar} nickname={friend.nickname} color={friend.color} size={72} />
          <div>
            <p className="friend-profile__tag">#{friend.tag}</p>
            {state.status === 'ready' && <p className="muted">Member since {monthYear(state.data.memberSince)}</p>}
          </div>
        </div>
        <StatsSection stats={stats} onRetry={retry} />
        <ByGameSection stats={stats} onRetry={retry} />
      </div>
    </Modal>
  )
}

// ----- requests and blocked tabs ------------------------------------------------------

function RequestsTab({ data }: { data: FriendsOverview }) {
  const social = useSocial()
  const { toast } = useRoomActions()
  const [busy, setBusy] = useState<number | null>(null)

  const act = async (request: FriendRequestEntry, work: () => Promise<unknown>, done: string, list: 'incoming' | 'outgoing') => {
    setBusy(request.requestId)
    try {
      await work()
      social.update((d) => ({ ...d, [list]: d[list].filter((r) => r.requestId !== request.requestId) }))
      toast(done)
      if (done.startsWith('You and')) social.refresh()
    } catch (err) {
      toast(socialError(err), 'error')
      social.refresh()
    } finally {
      setBusy(null)
    }
  }

  return (
    <>
      <section className="stack" aria-labelledby="incoming-heading">
        <h2 id="incoming-heading">Waiting for you</h2>
        {data.incoming.length === 0 ? (
          <p className="muted">No requests right now.</p>
        ) : (
          <ul className="friend-list">
            {data.incoming.map((r) => (
              <PlayerRow key={r.requestId} player={r}>
                <span className="friend-row__buttons">
                  <Button
                    disabled={busy === r.requestId}
                    onClick={() => act(r, () => acceptRequest(r.requestId), `You and ${r.nickname} are now friends!`, 'incoming')}
                    aria-label={`Accept ${r.nickname}`}
                  >
                    Accept
                  </Button>
                  <Button
                    variant="secondary"
                    disabled={busy === r.requestId}
                    onClick={() => act(r, () => declineRequest(r.requestId), 'Request declined.', 'incoming')}
                    aria-label={`Decline ${r.nickname}`}
                  >
                    Decline
                  </Button>
                </span>
              </PlayerRow>
            ))}
          </ul>
        )}
      </section>
      <section className="stack" aria-labelledby="outgoing-heading">
        <h2 id="outgoing-heading">Sent by you</h2>
        {data.outgoing.length === 0 ? (
          <p className="muted">You have no requests waiting.</p>
        ) : (
          <ul className="friend-list">
            {data.outgoing.map((r) => (
              <PlayerRow key={r.requestId} player={r}>
                <Button
                  variant="secondary"
                  disabled={busy === r.requestId}
                  onClick={() => act(r, () => cancelRequest(r.requestId), 'Request cancelled.', 'outgoing')}
                  aria-label={`Cancel request to ${r.nickname}`}
                >
                  Cancel
                </Button>
              </PlayerRow>
            ))}
          </ul>
        )}
      </section>
    </>
  )
}

function BlockedTab({ data }: { data: FriendsOverview }) {
  const social = useSocial()
  const { toast } = useRoomActions()
  const [busy, setBusy] = useState<string | null>(null)
  if (data.blocked.length === 0) {
    return (
      <EmptyState icon="🛡️" title="Nobody is blocked">
        Players you block show up here, and you can unblock them any time.
      </EmptyState>
    )
  }
  return (
    <ul className="friend-list">
      {data.blocked.map((p) => (
        <PlayerRow key={p.tag} player={p}>
          <Button
            variant="secondary"
            disabled={busy === p.tag}
            aria-label={`Unblock ${p.nickname}`}
            onClick={async () => {
              setBusy(p.tag)
              try {
                await unblockPlayer(p.tag)
                social.update((d) => ({ ...d, blocked: d.blocked.filter((b) => b.tag !== p.tag) }))
                toast(`${p.nickname} is unblocked.`)
              } catch (err) {
                toast(socialError(err), 'error')
              } finally {
                setBusy(null)
              }
            }}
          >
            Unblock
          </Button>
        </PlayerRow>
      ))}
    </ul>
  )
}
