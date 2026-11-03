import { useCallback, useEffect, useState } from 'react'
import { Button } from '../../components/Button'
import { StatusLabel } from '../../components/StatusLabel'
import { fetchSettings, friendRequestError, saveDiscoverable, sendFriendRequest } from '../../lib/social'
import { useRoomActions } from '../../state/context'
import { useSocial } from '../../state/socialContext'
import type { DiscoverPlayer } from '../../types/protocol'
import { RingAvatar } from '../profile/ProfileSections'

const REFRESH_MS = 30_000

/** "People online": players who opted in to be found, so anyone can send them a request.
 *  Your own listing is opt-in too (the switch at the top). */
export function PeopleOnline() {
  const { socket, toast } = useRoomActions()
  const social = useSocial()
  const [listed, setListed] = useState<boolean | null>(null)
  const [players, setPlayers] = useState<DiscoverPlayer[] | null>(null)
  const [busy, setBusy] = useState<string | null>(null)

  const load = useCallback(() => {
    socket
      .request('friends:discover', {})
      .then((data) => setPlayers(data.players))
      .catch(() => setPlayers((prev) => prev ?? []))
  }, [socket])

  useEffect(() => {
    let live = true
    fetchSettings()
      .then((s) => live && setListed(Boolean(s.discoverable)))
      .catch(() => {})
    load()
    const timer = setInterval(load, REFRESH_MS)
    return () => {
      live = false
      clearInterval(timer)
    }
  }, [load])

  const toggle = async () => {
    const next = !listed
    setListed(next)
    try {
      setListed((await saveDiscoverable(next)).discoverable)
      toast(next ? "You're listed in People online." : "You're no longer listed.")
    } catch {
      setListed(!next)
      toast('Could not change that. Try again.', 'error')
    }
  }

  const add = async (player: DiscoverPlayer) => {
    setBusy(player.tag)
    try {
      const result = await sendFriendRequest(player.tag)
      toast(result.status === 'friends' ? `You and ${player.nickname} are now friends!` : `Request sent to ${player.nickname}.`)
      setPlayers((list) => (list ?? []).map((p) => (p.tag === player.tag ? { ...p, relationship: result.status === 'friends' ? 'friends' : 'requested' } : p)))
      social.refresh()
    } catch (err) {
      toast(friendRequestError(err), 'error')
    } finally {
      setBusy(null)
    }
  }

  return (
    <section className="stack" aria-labelledby="people-online-heading">
      <h2 id="people-online-heading">People online</h2>
      <p className="muted">Players online now who want to make new friends. Tap Add friend to send a request.</p>
      <label className="people-online__switch">
        <input type="checkbox" checked={Boolean(listed)} disabled={listed === null} onChange={() => void toggle()} />
        <span>Show me here so other players can add me</span>
      </label>
      {players === null ? (
        <p className="muted">Looking for players…</p>
      ) : players.length === 0 ? (
        <p className="muted">Nobody else is listed right now. Check back soon.</p>
      ) : (
        <ul className="friend-list" aria-label="Players online now">
          {players.map((p) => (
            <li key={p.tag} className="friend-row">
              <RingAvatar avatar={p.avatar} nickname={p.nickname} color={p.color} size={44} />
              <span className="friend-row__who">
                <span className="friend-row__name">{p.nickname}</span>
                <span className="muted friend-row__tag">#{p.tag}</span>
                <StatusLabel status={p.status} />
              </span>
              <span className="friend-row__end">
                {p.relationship === 'none' ? (
                  <Button variant="secondary" disabled={busy === p.tag} onClick={() => void add(p)}>
                    Add friend
                  </Button>
                ) : (
                  <span className="muted">
                    {p.relationship === 'requested' ? 'Requested' : p.relationship === 'incoming' ? 'Wants to be friends' : 'Friends'}
                  </span>
                )}
              </span>
            </li>
          ))}
        </ul>
      )}
      <Button variant="ghost" onClick={load}>
        Refresh
      </Button>
    </section>
  )
}
