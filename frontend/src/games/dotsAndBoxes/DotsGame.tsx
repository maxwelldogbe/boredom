import { useEffect, useState, type KeyboardEvent } from 'react'
import { PlayerCards } from '../../components/PlayerCards'
import { TimerBar } from '../../components/TimerBar'
import { C } from '../../lib/constants'
import { nameOf, playerById } from '../../lib/players'
import { seatColor } from '../../lib/seatColors'
import type { RoomPublic } from '../../types/protocol'
import type { DotsView } from '../../types/views'
import type { GameUiProps } from '../types'
import './dots.css'

const GAP = 40 // viewBox units between dots
const PAD = 12

interface LineGeom {
  id: string
  x1: number
  y1: number
  x2: number
  y2: number
  label: string
}

/** Every line on the board with its SVG coordinates (ids as in core/PROTOCOL.md 7.4). */
function boardLines(size: number): LineGeom[] {
  const at = (n: number) => PAD + n * GAP
  const lines: LineGeom[] = []
  for (let r = 0; r <= size; r++) {
    for (let c = 0; c < size; c++) {
      lines.push({ id: `h:${r}:${c}`, x1: at(c), y1: at(r), x2: at(c + 1), y2: at(r), label: `Horizontal line, row ${r + 1}, column ${c + 1}` })
    }
  }
  for (let r = 0; r < size; r++) {
    for (let c = 0; c <= size; c++) {
      lines.push({ id: `v:${r}:${c}`, x1: at(c), y1: at(r), x2: at(c), y2: at(r + 1), label: `Vertical line, row ${r + 1}, column ${c + 1}` })
    }
  }
  return lines
}

/** Dots and Boxes (plan section 10). The whole board is public. */
export function DotsGame({ view, send, me, room }: GameUiProps<DotsView>) {
  const [pending, setPending] = useState<string | null>(null)
  const canDraw = view.isYourTurn && pending === null
  const extent = PAD * 2 + view.size * GAP
  const at = (n: number) => PAD + n * GAP

  const draw = async (id: string) => {
    if (!canDraw || view.lines[id]) return
    setPending(id)
    await send({ type: 'drawLine', id })
    setPending(null)
  }
  const onKey = (e: KeyboardEvent, id: string) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault()
      void draw(id)
    }
  }

  return (
    <div className="stack dots">
      <TurnBanner view={view} me={me} room={room} />
      {view.phase === 'playing' && <TimerBar deadline={view.turnDeadline} totalMs={C.DOTS_TURN_MS} label="Turn time left" />}

      <PlayerCards
        room={room}
        me={me}
        activeId={view.currentPlayerId}
        label="Players and boxes"
        entries={view.order.map((id) => ({ id, value: view.scores[id] ?? 0, valueLabel: `${view.scores[id] ?? 0} boxes` }))}
      />

      <svg
        className="dots__board"
        viewBox={`0 0 ${extent} ${extent}`}
        role="group"
        aria-label="Board"
        style={{ background: '#FFFFFF' }}
      >
        {view.boxes.map((row, r) =>
          row.map((owner, c) => {
            if (!owner) return null
            const p = playerById(room, owner)
            return (
              <g key={`b${r}:${c}`} aria-label={`Box owned by ${nameOf(room, owner, me)}`}>
                <text
                  x={at(c) + GAP / 2}
                  y={at(r) + GAP / 2}
                  className="dots__initial"
                  fill={seatColor(room, owner)}
                  fillOpacity={1}
                >
                  {p.nickname.charAt(0).toUpperCase()}
                </text>
              </g>
            )
          }),
        )}
        {boardLines(view.size).map((line) => {
          const owner = view.lines[line.id]
          const isLast = view.lastMove?.lineId === line.id
          const free = !owner
          return (
            <g key={line.id}>
              <line
                {...pick(line)}
                className={`dots__line${owner ? ' dots__line--drawn' : ''}${isLast ? ' dots__line--last' : ''}`}
                stroke="#000000"
                strokeWidth={owner ? 8 : 2}
                strokeDasharray={owner ? undefined : '4 6'}
                strokeLinecap={owner ? 'butt' : 'round'}
              />
              {free && canDraw && (
                <line
                  {...pick(line)}
                  className="dots__hit"
                  role="button"
                  tabIndex={0}
                  aria-label={line.label}
                  onClick={() => draw(line.id)}
                  onKeyDown={(e) => onKey(e, line.id)}
                />
              )}
            </g>
          )
        })}
        {Array.from({ length: (view.size + 1) ** 2 }, (_, i) => (
          <circle key={i} cx={at(i % (view.size + 1))} cy={at(Math.floor(i / (view.size + 1)))} r={5} fill="#A3A3A3" className="dots__dot" />
        ))}
      </svg>

    </div>
  )
}

function pick({ x1, y1, x2, y2 }: LineGeom) {
  return { x1, y1, x2, y2 }
}

function TurnBanner({ view, me, room }: { view: DotsView; me: string; room: RoomPublic }) {
  const [visibleAutoMove, setVisibleAutoMove] = useState(view.lastMove?.auto ? view.lastMove : null)
  const autoWho = view.lastMove ? nameOf(room, view.lastMove.playerId, me) : ''
  useEffect(() => {
    if (!view.lastMove?.auto) return
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setVisibleAutoMove(view.lastMove)
    const timer = window.setTimeout(() => setVisibleAutoMove(null), 4000)
    return () => window.clearTimeout(timer)
  }, [view.lastMove])
  return (
    <div className="stack dots__banner" role="status">
      {view.phase === 'done' && <p className="dots__turn">All boxes are claimed! Results coming up…</p>}
      {visibleAutoMove && (
        <p className="muted dots__note">
          {visibleAutoMove.auto === 'timeout' ? '⌛ Time ran out' : '📴 Offline'}: a line was drawn for {autoWho === 'You' ? 'you' : autoWho}.
        </p>
      )}
      {view.phase === 'playing' && view.lastMove && view.lastMove.boxes.length > 0 && (
        <p className="muted dots__note">
          {autoWho} closed {view.lastMove.boxes.length === 1 ? 'a box' : `${view.lastMove.boxes.length} boxes`} and goes again.
        </p>
      )}
    </div>
  )
}
