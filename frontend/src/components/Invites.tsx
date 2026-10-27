/** Room invites between friends (core/PROTOCOL.md 9.4): the lobby's "Invite friends" sheet, the
 *  "Invite to play" button on friend rows, and the banners for invites received. Registered
 *  players only. */
import { useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { gameUi } from '../games/registry'
import { C } from '../lib/constants'
import { friendlyError } from '../lib/errors'
import { inviteAcceptError, inviteSendError, STATUS_ORDER, type Friend } from '../lib/social'
import { RingAvatar } from '../pages/profile/ProfileSections'
import { useRoomActions, useRoomState } from '../state/context'
import { useSocial, type ReceivedInvite } from '../state/socialContext'
import { useNow } from '../state/useCountdown'
import { Button } from './Button'
import { EmptyState, Loading } from './EmptyState'
import { Modal } from './Modal'
import { StatusLabel } from './StatusLabel'

const MAX_BANNERS = 3

/** True while a friend invited at `sentAt` is still in the cooldown. */
const inCooldown = (sentAt: number | undefined, now: number) => sentAt !== undefined && now - sentAt < C.INVITE_COOLDOWN_MS

const sortFriends = (friends: Friend[]) =>
  [...friends].sort(
    (a, b) => STATUS_ORDER.indexOf(a.status) - STATUS_ORDER.indexOf(b.status) || a.nickname.localeCompare(b.nickname),
  )

// ----- lobby -------------------------------------------------------------------------

/** The lobby's big "Invite friends" button and its bottom sheet. */
export function InviteFriendsButton() {
  const [open, setOpen] = useState(false)
  return (
    <>
      <Button block className="invite-friends" onClick={() => setOpen(true)}>
        <span aria-hidden="true">👥 </span>
        Invite friends
      </Button>
      {open && <InviteSheet onClose={() => setOpen(false)} />}
    </>
  )
}

function InviteSheet({ onClose }: { onClose: () => void }) {
  const social = useSocial()
  const now = useNow(1000)
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const overview = social.overview

  const invite = async (friend: Friend) => {
    setBusy(friend.tag)
    setError(null)
    try {
      await social.sendInvite(friend)
    } catch (err) {
      setError(inviteSendError(err))
    } finally {
      setBusy(null)
    }
  }

  return (
    <Modal
      title="Invite friends"
      className="modal--sheet"
      onClose={onClose}
      actions={
        <Button variant="secondary" block onClick={onClose}>
          Close
        </Button>
      }
    >
      {error && (
        <p className="field__error" role="alert">
          {error}
        </p>
      )}
      {overview.status === 'error' ? (
        <div className="stack">
          <p className="field__error" role="alert">
            {overview.message}
          </p>
          <Button variant="secondary" onClick={social.refresh}>
            Try again
          </Button>
        </div>
      ) : overview.status !== 'ready' ? (
        <Loading label="Loading your friends…" />
      ) : overview.data.friends.length === 0 ? (
        <EmptyState icon="👋" title="No friends yet. Add friends from the Friends page.">
          <Link to="/friends">Go to Friends</Link>
        </EmptyState>
      ) : (
        <ul className="friend-list">
          {sortFriends(overview.data.friends).map((f) => {
            const sent = inCooldown(social.sentAt[f.tag], now)
            return (
              <li key={f.tag} className="friend-row">
                <RingAvatar avatar={f.avatar} nickname={f.nickname} color={f.color} size={40} />
                <span className="friend-row__who">
                  <span className="friend-row__name">{f.nickname}</span>
                  <StatusLabel status={f.status} />
                </span>
                <span className="friend-row__end">
                  {sent ? (
                    <Button variant="secondary" disabled>
                      Sent
                    </Button>
                  ) : f.status === 'online' ? (
                    <Button disabled={busy !== null} onClick={() => void invite(f)} aria-label={`Invite ${f.nickname}`}>
                      {busy === f.tag ? 'Sending…' : 'Invite'}
                    </Button>
                  ) : (
                    <Button variant="secondary" disabled>
                      Unavailable
                    </Button>
                  )}
                </span>
              </li>
            )
          })}
        </ul>
      )}
    </Modal>
  )
}

// ----- friend rows -------------------------------------------------------------------

let settingUp = false // one room at a time, whichever row was tapped

/** "Invite to play" on an online friend's row: invites from the current lobby, or sets up a
 *  room first and then invites. Disabled while the player is in a running game. */
export function InviteToPlayButton({ friend }: { friend: Friend }) {
  const social = useSocial()
  const { room } = useRoomState()
  const { createRoom, toast } = useRoomActions()
  const navigate = useNavigate()
  const now = useNow(1000)
  const [step, setStep] = useState<'idle' | 'room' | 'invite'>('idle')

  if (room && room.status !== 'lobby') {
    return (
      <Button variant="secondary" disabled aria-label={`Invite ${friend.nickname} to play: you are in a game`}>
        In a game
      </Button>
    )
  }

  const invite = async () => {
    if (room) {
      setStep('invite')
      try {
        await social.sendInvite(friend)
        toast('Invite sent')
      } catch (err) {
        toast(inviteSendError(err), 'error')
      } finally {
        setStep('idle')
      }
      return
    }
    if (settingUp) return
    if (social.statusOf(friend.tag) !== 'online') {
      toast(`${friend.nickname} can't be invited right now.`, 'error')
      return
    }
    settingUp = true
    setStep('room')
    let code: string
    try {
      code = await createRoom()
    } catch (err) {
      settingUp = false
      setStep('idle')
      toast(`We couldn't set up a room. ${friendlyError(err)}`, 'error')
      return
    }
    setStep('invite')
    try {
      await social.sendInvite(friend)
      toast('Invite sent')
    } catch (err) {
      toast(`Your room is ready, but the invite didn't go through. ${inviteSendError(err)}`, 'error')
    } finally {
      settingUp = false
    }
    navigate(`/room/${code}`)
  }

  const sent = inCooldown(social.sentAt[friend.tag], now)
  const label = step === 'room' ? 'Setting up your room…' : step === 'invite' ? 'Sending…' : sent ? 'Invite sent' : 'Invite to play'
  return (
    <span aria-live="polite">
      <Button
        disabled={step !== 'idle' || sent}
        onClick={() => void invite()}
        aria-label={step === 'idle' && !sent ? `Invite ${friend.nickname} to play` : undefined}
      >
        {label}
      </Button>
    </span>
  )
}

// ----- banners -----------------------------------------------------------------------

/** Invites received, at the top of every screen except inside a room. */
export function InviteBanners() {
  const social = useSocial()
  const { pathname } = useLocation()
  const now = useNow(1000)
  if (!social.signedIn || pathname.startsWith('/room/') || pathname.startsWith('/admin')) return null
  const live = social.invites.filter((i) => i.localExpiresAt > now).slice(0, MAX_BANNERS)
  if (live.length === 0) return null
  return (
    <div className="invite-banners" aria-label="Invites">
      {live.map((i) => (
        <InviteBanner key={i.inviteId} invite={i} now={now} />
      ))}
    </div>
  )
}

function InviteBanner({ invite, now }: { invite: ReceivedInvite; now: number }) {
  const social = useSocial()
  const { toast } = useRoomActions()
  const navigate = useNavigate()
  const [busy, setBusy] = useState(false)
  const game = gameUi(invite.gameId)
  // `now` ticks once a second, so it can be a little older than the invite.
  const ms = Math.min(invite.localExpiresAt - now, invite.expiresAt - invite.serverNow)
  const seconds = Math.max(0, Math.ceil(ms / 1000))
  const left = `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`

  const join = async () => {
    setBusy(true)
    try {
      const code = await social.acceptInvite(invite.inviteId)
      navigate(`/join/${code}`)
    } catch (err) {
      setBusy(false)
      toast(inviteAcceptError(err), 'error')
    }
  }

  return (
    <section className="invite-banner" role="status" aria-label={`Invite from ${invite.fromNickname}`}>
      <RingAvatar avatar={invite.fromAvatar} nickname={invite.fromNickname} color="var(--primary)" size={40} />
      <div className="invite-banner__text">
        <p className="invite-banner__title">
          <strong>{invite.fromNickname}</strong> invited you to play
          {game ? (
            <>
              {' '}
              <strong>{game.name}</strong>
            </>
          ) : null}
        </p>
        <p className="muted invite-banner__time">
          Expires in <span className="invite-banner__left">{left}</span>
        </p>
      </div>
      <div className="invite-banner__buttons">
        <Button disabled={busy} onClick={() => void join()} aria-label={`Join ${invite.fromNickname}`}>
          {busy ? 'Joining…' : 'Join'}
        </Button>
        <Button
          variant="secondary"
          disabled={busy}
          onClick={() => social.declineInvite(invite.inviteId)}
          aria-label={`Decline ${invite.fromNickname}`}
        >
          Decline
        </Button>
      </div>
    </section>
  )
}

/** Online friends with "Invite to play", for the home screen. */
export function OnlineFriends() {
  const social = useSocial()
  if (!social.signedIn || social.overview.status !== 'ready') return null
  const online = social.overview.data.friends.filter((f) => f.status === 'online')
  if (online.length === 0) return null
  return (
    <section className="stack home__online" aria-labelledby="online-friends">
      <h2 id="online-friends" className="section-title">
        Friends online
      </h2>
      <ul className="friend-list">
        {sortFriends(online).map((f) => (
          <li key={f.tag} className="friend-row">
            <RingAvatar avatar={f.avatar} nickname={f.nickname} color={f.color} size={40} />
            <span className="friend-row__who">
              <span className="friend-row__name">{f.nickname}</span>
              <StatusLabel status={f.status} />
            </span>
            <span className="friend-row__end">
              <InviteToPlayButton friend={f} />
            </span>
          </li>
        ))}
      </ul>
    </section>
  )
}
