import { Link } from 'react-router-dom'
import { CommunityLink } from '../components/CommunityLink'
import { getProfile } from '../lib/profileStore'
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
      <WhatWeSave registered={registered} heading="What we record" community />
    </main>
  )
}
