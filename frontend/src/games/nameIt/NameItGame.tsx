import { useState, type FormEvent } from 'react'
import { Button } from '../../components/Button'
import { CountdownRing } from '../../components/CountdownRing'
import { PlayerChip } from '../../components/PlayerChip'
import { TextInput } from '../../components/TextInput'
import { TimerBar } from '../../components/TimerBar'
import { C } from '../../lib/constants'
import { nameOf, playerById } from '../../lib/players'
import { useRemainingMs } from '../../state/useCountdown'
import type { NameItView } from '../../types/views'
import type { GameUiProps } from '../types'
import './nameIt.css'

const TEXT_MAX = 40

const REASONS = { timeout: 'ran out of time', duplicate: 'repeated an answer', challenge: 'lost a challenge' }

/** Name It Survival (plan section 12). Votes are secret until the vote closes. */
export function NameItGame({ view, send, me, room }: GameUiProps<NameItView>) {
  return (
    <div className="stack name-it">
      <EliminationBanner view={view} me={me} room={room} />
      {view.phase === 'topicSelect' && <TopicSelect view={view} send={send} me={me} room={room} />}
      {(view.phase === 'turn' || view.phase === 'challenge') && (
        <>
          <div className="name-it__topic">
            <span className="muted">Topic</span>
            <strong>{view.topic}</strong>
          </div>
          <TurnStatus view={view} me={me} room={room} />
          {view.phase === 'challenge' && view.challenge && <VotePanel view={view} send={send} me={me} room={room} />}
          {view.isYourTurn && <AnswerForm key={view.used.length} send={send} />}
          <ChallengeButton view={view} send={send} me={me} room={room} />
          <UsedList view={view} me={me} room={room} />
        </>
      )}
      {view.phase === 'done' && <p className="name-it__status">Last one standing! Results coming up…</p>}
      <Players view={view} me={me} room={room} />
    </div>
  )
}

type Part = Pick<GameUiProps<NameItView>, 'view' | 'me' | 'room'>
type ActPart = Pick<GameUiProps<NameItView>, 'view' | 'send' | 'me' | 'room'>

function EliminationBanner({ view, me, room }: Part) {
  const e = view.lastElimination
  if (!e) return null
  const who = nameOf(room, e.playerId, me)
  return (
    <p className="name-it__banner" role="status">
      ✖ {who} {REASONS[e.reason]}
      {e.text ? ` (“${e.text}”)` : ''}
      {e.playerId === me ? ' and you are out.' : ' and is out.'}
    </p>
  )
}

function TopicSelect({ view, send, me, room }: ActPart) {
  const [custom, setCustom] = useState('')
  const [sending, setSending] = useState(false)
  const choose = async (topic: string) => {
    setSending(true)
    if (!(await send({ type: 'chooseTopic', topic }))) setSending(false)
  }
  const submit = (e: FormEvent) => {
    e.preventDefault()
    if (custom.trim()) void choose(custom.trim())
  }
  const ring = <CountdownRing deadline={view.topicDeadline} totalMs={C.NAMEIT_TOPIC_MS} />
  if (!view.isTopicChooser) {
    return (
      <div className="name-it__waiting" role="status">
        {ring}
        <p>⏳ Waiting for {nameOf(room, view.topicChooserId, me)} to choose a topic…</p>
      </div>
    )
  }
  return (
    <section className="stack" aria-label="Choose a topic">
      <div className="name-it__waiting">
        {ring}
        <p>Pick the next topic! If time runs out, one is picked for you.</p>
      </div>
      <div className="name-it__suggestions">
        {view.suggestions.map((t) => (
          <Button key={t} variant="secondary" block disabled={sending} onClick={() => choose(t)}>
            {t}
          </Button>
        ))}
      </div>
      {view.settings.allowCustomTopics && (
        <form className="stack" onSubmit={submit} noValidate>
          <TextInput label="Or type your own" value={custom} onChange={(e) => setCustom(e.target.value)} maxLength={TEXT_MAX} autoComplete="off" />
          <Button type="submit" block disabled={sending || !custom.trim()}>
            Use this topic
          </Button>
        </form>
      )}
    </section>
  )
}

function TurnStatus({ view, me, room }: Part) {
  const totalMs = view.settings.turnSeconds * 1000
  return (
    <div className="name-it__turn" role="status">
      {view.phase === 'turn' && <CountdownRing deadline={view.turnDeadline} totalMs={totalMs} />}
      <p>
        {view.phase === 'challenge'
          ? '⏸ Paused for a challenge'
          : view.isYourTurn
            ? 'Your turn! Name something.'
            : `${nameOf(room, view.currentPlayerId, me)} is answering…`}
      </p>
    </div>
  )
}

function AnswerForm({ send }: Pick<GameUiProps<NameItView>, 'send'>) {
  const [text, setText] = useState('')
  const [sending, setSending] = useState(false)
  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (!text.trim()) return
    setSending(true)
    if (!(await send({ type: 'submitAnswer', text: text.trim() }))) setSending(false)
  }
  return (
    <form className="name-it__answer" onSubmit={submit} noValidate>
      <TextInput
        label="Your answer"
        value={text}
        onChange={(e) => setText(e.target.value)}
        maxLength={TEXT_MAX}
        autoComplete="off"
        autoFocus
      />
      <Button type="submit" block disabled={sending || !text.trim()}>
        Submit
      </Button>
    </form>
  )
}

function ChallengeButton({ view, send, me, room }: ActPart) {
  const left = useRemainingMs(view.challengeWindow?.until ?? null)
  const [sending, setSending] = useState(false)
  if (!view.canChallenge || !view.challengeWindow || !left) return null
  const answer = view.used[view.challengeWindow.answerIndex]
  const challenge = async () => {
    setSending(true)
    await send({ type: 'challenge' })
    setSending(false)
  }
  return (
    <section className="stack name-it__challenge" aria-label="Challenge">
      <Button variant="danger" block disabled={sending} onClick={challenge}>
        Challenge “{answer.text}” by {nameOf(room, answer.playerId, me)}
      </Button>
      <TimerBar deadline={view.challengeWindow.until} totalMs={view.challengeWindowMs} label="Challenge window" />
    </section>
  )
}

function VotePanel({ view, send, me, room }: ActPart) {
  const c = view.challenge!
  const [sending, setSending] = useState(false)
  const vote = async (valid: boolean) => {
    setSending(true)
    if (!(await send({ type: 'vote', valid }))) setSending(false)
  }
  return (
    <section className="stack name-it__vote" aria-label="Vote">
      <p>
        <strong>{nameOf(room, c.challengerId, me)}</strong> challenged {nameOf(room, c.answererId, me)}'s answer{' '}
        <strong>“{c.text}”</strong>.
      </p>
      <TimerBar deadline={c.deadline} totalMs={C.NAMEIT_VOTE_MS} label="Vote closes" />
      {c.canVote ? (
        <div className="name-it__vote-buttons">
          <Button variant="secondary" disabled={sending} onClick={() => vote(true)}>
            ✓ Valid
          </Button>
          <Button variant="danger" disabled={sending} onClick={() => vote(false)}>
            ✗ Invalid
          </Button>
        </div>
      ) : (
        <p className="muted">
          {c.hasVoted ? 'Vote cast. ' : ''}
          {c.voterIds.length === 0 ? 'No one else can vote.' : `Votes in: ${c.votedCount}/${c.voterIds.length}`}
        </p>
      )}
    </section>
  )
}

function UsedList({ view, me, room }: Part) {
  if (view.used.length === 0) return <p className="muted name-it__empty">No answers yet for this topic.</p>
  return (
    <section aria-label="Answers so far">
      <h2 className="name-it__title">Answers so far</h2>
      <ol className="name-it__used" reversed>
        {[...view.used].reverse().map((u, i) => (
          <li key={view.used.length - i}>
            <strong>{u.text}</strong> <span className="muted">· {nameOf(room, u.playerId, me)}</span>
          </li>
        ))}
      </ol>
    </section>
  )
}

function Players({ view, me, room }: Part) {
  return (
    <ul className="name-it__players" aria-label="Players">
      {view.order.map((pid) => {
        const out = !view.alive.includes(pid)
        const current = pid === view.currentPlayerId
        return (
          <li key={pid} className={`name-it__player${out ? ' name-it__player--out' : ''}${current ? ' name-it__player--turn' : ''}`}>
            <PlayerChip player={playerById(room, pid)} isMe={pid === me} size="sm" extra={out ? '✖ out' : undefined} />
          </li>
        )
      })}
    </ul>
  )
}
