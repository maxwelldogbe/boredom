import { communityUrl } from '../../config/community'
import { C } from '../../lib/constants'

/** Plain-language list of what the server stores, for guests and for account holders. */
export function WhatWeSave({
  registered,
  heading = 'What we save',
  community: withCommunity = false,
}: {
  registered: boolean
  heading?: string
  /** Add the line about community links (on /about). */
  community?: boolean
}) {
  const community = withCommunity && communityUrl() && <li>Links to our community open WhatsApp, which has its own privacy policy.</li>
  return (
    <section className="card stack what-we-save" aria-labelledby="what-we-save-heading">
      <h2 id="what-we-save-heading">{heading}</h2>
      {registered ? (
        <ul>
          <li>Your username and password (the password is stored scrambled, never as text).</li>
          <li>Your nickname, color, avatar, tag, the date you joined and your status setting.</li>
          <li>Your stats, and a record of the games you play (game, result and the nickname you used).</li>
          <li>Activity such as logging in and joining rooms, kept for {C.ACTIVITY_RETENTION_DAYS} days.</li>
          <li>Your friends, friend requests and the players you block.</li>
          <li>Reports you send and reports about you. Only our team sees them.</li>
          {community}
        </ul>
      ) : (
        <ul>
          <li>Your profile stays on this device. We don't store it on our server.</li>
          <li>Games you play are recorded with your nickname and a random id that doesn't identify you.</li>
          <li>If someone reports you in a room, the report keeps that random id and your nickname.</li>
          {community}
        </ul>
      )}
      {registered && (
        <p className="muted">
          Deleting your account removes your login, profile, stats, friends, requests and blocks. Game records stay
          only as anonymous totals, and reports stay without a link to you.
        </p>
      )}
    </section>
  )
}
