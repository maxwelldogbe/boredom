import { Link } from 'react-router-dom'
import { CommunityLink } from '../components/CommunityLink'
import { getProfile } from '../lib/profileStore'
import { PRESENCE_OPTIONS } from '../lib/social'
import { WhatWeSave } from './profile/WhatWeSave'

/** /about: what boredom is, our community, and what we record. */
export default function AboutPage() {
  const registered = getProfile()?.type === 'registered'
  return (
    <main className="page stack about">
      <Link to="/" className="back-link">
        ← Home
      </Link>
      <h1>About boredom</h1>
      <p className="muted">Party games for friends. One room code, everyone on their phone.</p>
      <CommunityLink note />
      <section className="card stack" id="statuses" aria-labelledby="statuses-heading">
        <h2 id="statuses-heading">Your status on Friends</h2>
        <p className="muted">Choose it at the top of the Friends page.</p>
        <dl className="about__statuses">
          {PRESENCE_OPTIONS.map((o) => (
            <div key={o.value}>
              <dt>{o.label}</dt>
              <dd>{o.hint}</dd>
            </div>
          ))}
        </dl>
      </section>
      <WhatWeSave registered={registered} heading="What we record" community />
    </main>
  )
}
