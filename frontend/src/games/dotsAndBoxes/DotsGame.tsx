import { useState, type KeyboardEvent } from 'react'
import { TimerBar } from '../../components/TimerBar'
import { C } from '../../lib/constants'
import { nameOf, playerById } from '../../lib/players'
import type { RoomPublic } from '../../types/protocol'
import type { DotsView } from '../../types/views'
import type { GameUiProps } from '../types'
import { playerColors } from './colors'
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
  const colors = playerColors(view.order)

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

      <svg className="dots__board" viewBox={`0 0 ${extent} ${extent}`} role="group" aria-label="Board">
        {view.boxes.map((row, r) =>
          row.map((owner, c) => {
            if (!owner) return null
            const p = playerById(room, owner)
            return (
              <g key={`b${r}:${c}`} aria-label={`Box owned by ${nameOf(room, owner, me)}`}>
                <rect x={at(c)} y={at(r)} width={GAP} height={GAP} fill={colors[owner]} className="dots__box" />
                <text x={at(c) + GAP / 2} y={at(r) + GAP / 2} className="dots__initial" fill={colors[owner]}>
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
                stroke={owner ? colors[owner] : undefined}
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
          <circle key={i} cx={at(i % (view.size + 1))} cy={at(Math.floor(i / (view.size + 1)))} r={4} className="dots__dot" />
        ))}
      </svg>

      <ul className="dots__legend" aria-label="Players and boxes">
        {view.order.map((pid) => (
          <li key={pid} className={`dots__legend-item${pid === view.currentPlayerId ? ' dots__legend-item--turn' : ''}`}>
            <span className="dots__swatch" style={{ background: colors[pid] }} aria-hidden="true" />
            <span className="dots__avatar" style={{ borderColor: colors[pid] }} aria-hidden="true">
              {nameOf(room, pid, me).charAt(0).toUpperCase()}
            </span>
            <span>{nameOf(room, pid, me)}</span>
            <strong aria-label={`${view.scores[pid] ?? 0} boxes`}>{view.scores[pid] ?? 0}</strong>
          </li>
        ))}
      </ul>
    </div>
  )
}

function pick({ x1, y1, x2, y2 }: LineGeom) {
  return { x1, y1, x2, y2 }
}

function TurnBanner({ view, me, room }: { view: DotsView; me: string; room: RoomPublic }) {
  const colors = playerColors(view.order)
  const auto = view.lastMove?.auto
  const autoWho = view.lastMove ? nameOf(room, view.lastMove.playerId, me) : ''
  return (
    <div className="stack dots__banner" role="status">
      {view.phase === 'done' ? (
        <p className="dots__turn">All boxes are claimed! Results coming up…</p>
      ) : view.isYourTurn ? (
        <p className="dots__turn dots__turn--me">Your turn: draw a line</p>
      ) : (
        <p className="dots__turn" style={{ color: view.currentPlayerId ? colors[view.currentPlayerId] : undefined }}>
          {nameOf(room, view.currentPlayerId, me)}'s turn
        </p>
      )}
      {auto && (
        <p className="muted dots__note">
          {auto === 'timeout' ? '⌛ Time ran out' : '📴 Offline'}: a line was drawn for {autoWho === 'You' ? 'you' : autoWho}.
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
