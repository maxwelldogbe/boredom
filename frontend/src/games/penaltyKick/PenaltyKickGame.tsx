import { useEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from 'react'
import { TimerBar } from '../../components/TimerBar'
import { C } from '../../lib/constants'
import { nameOf } from '../../lib/players'
import { useRoomState } from '../../state/context'
import { useRemainingMs } from '../../state/useCountdown'
import type { RoomPublic } from '../../types/protocol'
import type { GoalPoint, PenaltyGame, PenaltyKickView, PenaltyOutcome } from '../../types/views'
import { MATCH_SEAT_COLORS } from '../series/matchColors'
import { SeriesFrame } from '../series/SeriesFrame'
import type { GameUiProps } from '../types'
import {
  aimFromRelease,
  ballAt,
  ballEnd,
  clientToSvg,
  diveFromSwipe,
  isShortSwipe,
  keeperAt,
  keeperPose,
  KEEPER_HOME,
  nearBall,
  powerFromSpeed,
  showTarget,
  SPOT,
  swipeSpeed,
  type Pt,
  type Sample,
} from './geometry'
import { PenaltyScene } from './PenaltyScene'
import './penaltyKick.css'

const BANNERS: Record<PenaltyOutcome, string> = {
  goal: 'GOAL!',
  saved: 'SAVED!',
  wide: 'WIDE!',
  over: 'OVER!',
  post: 'POST!',
  fizzled: 'WEAK!',
}
const SHOOT_HINT = 'Swipe from the ball to the spot you want. A faster flick = more power. Wild shots can miss.'
const SHORT_HINT = 'Swipe from the ball toward the goal'
const DIVE_HINT = 'Swipe to dive before the ball arrives!'
const HINT_MS = 2000

interface Drag {
  id: number
  mode: 'shoot' | 'dive'
  startSvg: Pt
  samples: Sample[]
}

/** Penalty kick (PROTOCOL.md 7.10): swipe to shoot, swipe to dive while the ball flies. */
export function PenaltyKickGame({ view, send, me, room }: GameUiProps<PenaltyKickView>) {
  const match = view.match
  const game = match?.game ?? null
  return (
    <SeriesFrame
      view={view}
      me={me}
      room={room}
      send={send}
      activeId={game?.phase === 'aiming' ? game.shooter : null}
      scores={game?.scores}
      scoreLabel={(n) => `${n} ${n === 1 ? 'goal' : 'goals'}`}
      single
      thinking={false}
    >
      {game && match?.b && (
        <Pitch
          key={match.id}
          game={game}
          seats={[match.a, match.b]}
          role={view.role === 'player' ? (game.yourRole ?? null) : null}
          send={send}
          me={me}
          room={room}
        />
      )}
    </SeriesFrame>
  )
}

interface PitchProps {
  game: PenaltyGame
  seats: [string, string]
  role: PenaltyGame['yourRole']
  send: GameUiProps<PenaltyKickView>['send']
  me: string
  room: RoomPublic
}

function Pitch({ game, seats, role, send, me, room }: PitchProps) {
  const svgRef = useRef<SVGSVGElement>(null)
  const drag = useRef<Drag | null>(null)
  const [swipe, setSwipe] = useState<{ to: Pt; power: number } | null>(null)
  const [hint, setHint] = useState<string | null>(null)
  // Per kick: whether I shot or dived, and my dive (shown at once, before the server confirms).
  const [shotKick, setShotKick] = useState<number | null>(null)
  const [myDive, setMyDive] = useState<{ kick: number; at: GoalPoint } | null>(null)
  const now = useServerNow(game.phase === 'flight' || (game.phase === 'aiming' && Boolean(game.keeperPath?.length)))

  const flight = game.flight
  const kick = game.kickNo
  const canShoot = role === 'shooter' && game.phase === 'aiming' && shotKick !== kick
  const canDive = role === 'keeper' && game.phase === 'flight' && myDive?.kick !== kick
  const localDive = myDive?.kick === kick ? myDive.at : null

  useEffect(() => {
    if (!hint) return
    const timer = setTimeout(() => setHint(null), HINT_MS)
    return () => clearTimeout(timer)
  }, [hint])

  // No scrolling or pull-to-refresh while a swipe is in progress (touch-action covers most).
  useEffect(() => {
    const svg = svgRef.current
    if (!svg) return
    const block = (e: TouchEvent) => {
      if (drag.current) e.preventDefault()
    }
    svg.addEventListener('touchmove', block, { passive: false })
    return () => svg.removeEventListener('touchmove', block)
  }, [])

  const toSvg = (e: ReactPointerEvent<SVGSVGElement>) => clientToSvg(e.clientX, e.clientY, svgRef.current?.getScreenCTM?.() ?? null)
  const sample = (e: ReactPointerEvent<SVGSVGElement>): Sample => ({ x: e.clientX, y: e.clientY, t: e.timeStamp })

  const onPointerDown = (e: ReactPointerEvent<SVGSVGElement>) => {
    if (drag.current) return // extra fingers are ignored
    const at = toSvg(e)
    if (canShoot && nearBall(at)) drag.current = { id: e.pointerId, mode: 'shoot', startSvg: at, samples: [sample(e)] }
    else if (canDive) drag.current = { id: e.pointerId, mode: 'dive', startSvg: at, samples: [sample(e)] }
    else return
    e.preventDefault()
    e.currentTarget.setPointerCapture?.(e.pointerId)
  }

  const onPointerMove = (e: ReactPointerEvent<SVGSVGElement>) => {
    const d = drag.current
    if (!d || d.id !== e.pointerId) return
    d.samples.push(sample(e))
    if (d.mode === 'shoot') setSwipe({ to: toSvg(e), power: powerFromSpeed(swipeSpeed(d.samples)) })
  }

  const onPointerUp = (e: ReactPointerEvent<SVGSVGElement>) => {
    const d = drag.current
    if (!d || d.id !== e.pointerId) return
    drag.current = null
    setSwipe(null)
    const samples = [...d.samples, sample(e)]
    const end = toSvg(e)
    if (d.mode === 'shoot') {
      if (!canShoot) return
      if (isShortSwipe(samples[0], samples[samples.length - 1])) {
        setHint(SHORT_HINT)
        return
      }
      setShotKick(kick)
      const power = powerFromSpeed(swipeSpeed(samples))
      void send({ type: 'shoot', aim: aimFromRelease(end), power }).then((ok) => {
        if (!ok) setShotKick(null)
      })
    } else if (canDive) {
      const at = diveFromSwipe(flight?.keeperSpot ?? KEEPER_HOME, end.x - d.startSvg.x, end.y - d.startSvg.y)
      setMyDive({ kick, at })
      void send({ type: 'dive', ...at })
    }
  }

  const onPointerCancel = (e: ReactPointerEvent<SVGSVGElement>) => {
    if (drag.current?.id !== e.pointerId) return
    drag.current = null
    setSwipe(null)
  }

  // The keeper's pose: the server's dive, or mine at once during the flight.
  const serverDive = flight?.dive ? { x: flight.dive.x, y: flight.dive.y } : null
  const shownDive = game.phase === 'flight' ? (serverDive ?? localDive) : game.phase === 'result' ? serverDive : null
  const tooLate = game.phase === 'result' && localDive !== null && serverDive === null
  const spot = game.phase === 'aiming' ? keeperAt(game.keeperPath, now) : (flight?.keeperSpot ?? KEEPER_HOME)

  let ball = { ...SPOT, r: 17 }
  if (flight && game.phase === 'flight') {
    const end = ballEnd(flight.ball.to, flight.ball.power, null, null)
    const t = (now - flight.launchAt) / Math.max(1, flight.arriveAt - flight.launchAt)
    ball = ballAt(end, t, flight.ball.power < C.PENALTY_POWER_FIZZLE)
  } else if (flight && game.phase === 'result') {
    ball = ballAt(ballEnd(flight.ball.to, flight.ball.power, game.outcome, serverDive), 1, game.outcome === 'fizzled')
  }

  const seatOf = (id: string | null | undefined) => (id === seats[1] ? 1 : 0)
  const shooterId = game.shooter ?? game.lastKick?.shooter ?? null
  const keeperId = game.keeper ?? game.lastKick?.keeper ?? null
  const shooterName = nameOf(room, game.shooter, me)
  const keeperName = nameOf(room, game.keeper, me)

  let chip: string | null = hint
  if (!chip && canShoot) chip = SHOOT_HINT
  else if (!chip && canDive) chip = DIVE_HINT
  else if (!chip && game.phase === 'aiming' && role !== 'shooter') chip = `${shooterName} is lining up the shot...`

  const total = 2 * game.kicksPerPlayer
  const kickLabel = game.suddenDeath ? `Sudden death · Kick ${kick}` : `Kick ${kick} of ${total}`

  return (
    <div className="stack pk">
      {game.phase !== 'over' && <p className="pk__kick-no">{kickLabel}</p>}
      <KickTracker game={game} seats={seats} me={me} room={room} />
      {game.phase === 'aiming' && <TimerBar deadline={game.turnDeadline} totalMs={C.PENALTY_AIM_MS} label="Time to shoot" />}
      {game.phase === 'flight' && flight && <ReactBar now={now} launchAt={flight.launchAt} until={flight.arriveAt + flight.graceMs} />}
      <p className="visually-hidden" aria-live="polite">
        {announce(game, shooterName, keeperName)}
      </p>
      <div className={`pk-scene${canShoot || canDive ? ' pk-scene--active' : ''}`}>
        <PenaltyScene
          svgRef={svgRef}
          shooterColor={MATCH_SEAT_COLORS[seatOf(shooterId)]}
          keeperColor={MATCH_SEAT_COLORS[seatOf(keeperId)]}
          keeper={keeperPose(spot, shownDive)}
          ball={ball}
          trail={swipe ? { to: swipe.to, ring: showTarget(swipe.to) } : null}
          ripple={game.phase === 'result' && game.outcome === 'goal'}
          kicking={game.phase === 'flight'}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onPointerCancel={onPointerCancel}
        />
        {canShoot && <PowerMeter power={swipe?.power ?? 0} />}
        {tooLate && <p className="pk-scene__late">Too late</p>}
        {game.phase === 'result' && game.outcome && (
          <ResultBanner game={game} outcome={game.outcome} shooterName={shooterName} keeperName={keeperName} />
        )}
        {chip && <p className="pk-scene__chip">{chip}</p>}
      </div>
    </div>
  )
}

/** Server time (client clock plus the offset), redrawn every frame while `active`. */
function useServerNow(active: boolean): number {
  const { clockOffset } = useRoomState()
  const [now, setNow] = useState(() => Date.now() + clockOffset)
  useEffect(() => {
    if (!active || typeof requestAnimationFrame !== 'function') return
    let frame = 0
    const step = () => {
      setNow(Date.now() + clockOffset)
      frame = requestAnimationFrame(step)
    }
    frame = requestAnimationFrame(step)
    return () => cancelAnimationFrame(frame)
  }, [active, clockOffset])
  return now
}

function ReactBar({ now, launchAt, until }: { now: number; launchAt: number; until: number }) {
  const fraction = Math.max(0, Math.min(1, (until - now) / Math.max(1, until - launchAt)))
  return (
    <div className="pk-react" aria-hidden="true">
      <div className="pk-react__fill" style={{ width: `${fraction * 100}%` }} />
    </div>
  )
}

function PowerMeter({ power }: { power: number }) {
  const percent = Math.round(power * 100)
  return (
    <div className="pk-power">
      <span className="pk-power__label">Power</span>
      <div className="pk-power__track" role="meter" aria-label="Power" aria-valuemin={0} aria-valuemax={100} aria-valuenow={percent}>
        <div className="pk-power__fill" style={{ height: `${percent}%` }} />
      </div>
    </div>
  )
}

function ResultBanner({
  game,
  outcome,
  shooterName,
  keeperName,
}: {
  game: PenaltyGame
  outcome: PenaltyOutcome
  shooterName: string
  keeperName: string
}) {
  const remaining = useRemainingMs(game.resultUntil)
  return (
    <div className={`pk-banner pk-banner--${outcome}`}>
      <p className="pk-banner__title">{BANNERS[outcome]}</p>
      <p className="pk-banner__line">{resultLine(outcome, shooterName, keeperName)}</p>
      {!shootoutDecided(game) && remaining !== null && (
        <p className="pk-banner__next">Next kick in {Math.max(1, Math.ceil(remaining / 1000))}</p>
      )}
    </div>
  )
}

function resultLine(outcome: PenaltyOutcome, shooter: string, keeper: string): string {
  if (outcome === 'goal') return `${shooter} scored.`
  if (outcome === 'saved') return `${keeper} saved it.`
  return `${shooter} missed.`
}

function announce(game: PenaltyGame, shooter: string, keeper: string): string {
  if (game.phase === 'aiming') return `Kick ${game.kickNo}. ${shooter} shoots, ${keeper} keeps goal.`
  if (game.phase === 'flight') return 'The ball is in the air.'
  if (game.phase === 'result' && game.outcome) return `${BANNERS[game.outcome]} ${resultLine(game.outcome, shooter, keeper)}`
  return 'The shootout is over.'
}

/** Whether one side can no longer catch up (the server ends the shootout after this result). */
function shootoutDecided(game: PenaltyGame): boolean {
  const ids = Object.keys(game.scores)
  if (ids.length !== 2) return false
  const owed = Math.max(game.kicksPerPlayer, Math.floor((game.kicks.length + 1) / 2))
  const taken = (id: string) => game.kicks.filter((k) => k.shooter === id).length
  const [a, b] = ids
  const sa = game.scores[a] ?? 0
  const sb = game.scores[b] ?? 0
  return sa > sb + owed - taken(b) || sb > sa + owed - taken(a)
}

function KickTracker({ game, seats, me, room }: { game: PenaltyGame; seats: [string, string]; me: string; room: RoomPublic }) {
  return (
    <ul className="pk__tracker" aria-label="Kicks">
      {seats.map((id) => {
        const mine = game.kicks.filter((k) => k.shooter === id)
        const goals = mine.filter((k) => k.outcome === 'goal').length
        const left = Math.max(0, game.kicksPerPlayer - mine.length)
        return (
          <li key={id} className="pk__tracker-row">
            <span className="pk__tracker-name">{nameOf(room, id, me)}</span>
            <span className="visually-hidden">
              {goals} of {mine.length} {mine.length === 1 ? 'kick' : 'kicks'} scored
            </span>
            <span className="pk__dots" aria-hidden="true">
              {mine.map((k) => (k.outcome === 'goal' ? '●' : '○')).join(' ')}
              {left > 0 && <span className="pk__dots-left">{' ·'.repeat(left)}</span>}
            </span>
          </li>
        )
      })}
    </ul>
  )
}
