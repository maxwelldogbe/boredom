import { useState } from 'react'
import { TimerBar } from '../../components/TimerBar'
import { C } from '../../lib/constants'
import { nameOf } from '../../lib/players'
import type { CheckersMove, CheckersView, Square } from '../../types/views'
import { MATCH_SEAT_COLORS } from '../series/matchColors'
import { SeriesFrame } from '../series/SeriesFrame'
import type { GameUiProps } from '../types'
import './checkers.css'

const SIZE = 8
const SEAT_NAMES = ['red', 'blue']
const key = ([r, c]: Square) => `${r}:${c}`

/** Checkers (PROTOCOL.md 7.11). Every move comes from the server's legalMoves; nothing is computed here. */
export function CheckersGame({ view, send, me, room }: GameUiProps<CheckersView>) {
  const [picked, setPicked] = useState<string | null>(null)
  const [pending, setPending] = useState(false)
  const match = view.match
  const game = match?.game ?? null
  const legal: CheckersMove[] = view.role === 'player' && game?.isYourTurn ? (game.legalMoves ?? []) : []
  const canAct = legal.length > 0 && !pending
  const movable = new Map<string, CheckersMove[]>()
  for (const m of legal) movable.set(key(m.from), [...(movable.get(key(m.from)) ?? []), m])
  const forced = game?.forcedPiece ? key(game.forcedPiece) : null
  // A stale selection (the view moved on) simply stops matching any movable piece.
  const selected = forced ?? (picked && movable.has(picked) ? picked : null)
  const destinations = new Map((selected ? (movable.get(selected) ?? []) : []).map((m) => [key(m.to), m]))
  const mustCapture = legal.some((m) => m.captures.length > 0)
  const last = game?.lastMove ? new Set([key(game.lastMove.from), key(game.lastMove.to)]) : new Set<string>()
  const opponent = match && match.b ? (me === match.a ? match.b : match.a) : null
  const waiting = view.role === 'player' && game && game.turn !== null && !game.isYourTurn
  const lastGame = match?.lastGame
  const drawNotice = lastGame && lastGame.result === 'draw' && lastGame.gameNo === (match?.gameNo ?? 0) - 1 && lastGame.game.draw

  const tap = async (sq: string) => {
    if (!canAct) return
    const move = destinations.get(sq)
    if (move) {
      setPending(true)
      await send({ type: 'move', from: move.from, to: move.to })
      setPicked(null)
      setPending(false)
      return
    }
    if (forced) return
    setPicked(sq !== selected && movable.has(sq) ? sq : null)
  }

  return (
    <SeriesFrame view={view} me={me} room={room} send={send} activeId={game?.turn ?? null} single={view.bestOf === 1}>
      {game && (
        <div className="stack ck">
          {drawNotice && (
            <p className="series__notice" role="status">
              Draw: no captures or man moves for {lastGame.game.drawPlies} turns
            </p>
          )}
          {game.turn && (
            <div className="ck__timer">
              <TimerBar deadline={game.turnDeadline} totalMs={C.CHECKERS_TURN_MS} label="Turn time left" />
            </div>
          )}
          {waiting && <p className="ck__label">Waiting for {nameOf(room, opponent, me)}</p>}
          {canAct && mustCapture && <p className="ck__label">{forced ? 'Keep jumping: the same piece must capture again' : 'You must capture'}</p>}
          <div className={`ck__board${waiting ? ' ck__board--waiting' : ''}`} role="group" aria-label="Board">
            {Array.from({ length: SIZE * SIZE }, (_, i) => {
              const r = Math.floor(i / SIZE)
              const c = i % SIZE
              const sq = `${r}:${c}`
              if ((r + c) % 2 === 0) return <span key={sq} className="ck__sq ck__sq--light" aria-hidden="true" onClick={() => void tap(sq)} />
              const piece = game.board[r][c]
              const isSelected = sq === selected
              const dest = destinations.get(sq)
              const capturer = mustCapture && movable.has(sq)
              const label = [
                `Row ${r + 1}, column ${c + 1}: ${piece ? `${SEAT_NAMES[piece.seat - 1]} ${piece.king ? 'king' : 'piece'}` : 'empty'}`,
                capturer ? 'must capture' : '',
                isSelected ? 'selected' : '',
                dest ? (dest.captures.length ? 'capture here' : 'move here') : '',
                last.has(sq) ? 'last move' : '',
              ]
                .filter(Boolean)
                .join(', ')
              return (
                <button
                  key={sq}
                  type="button"
                  className={[
                    'ck__sq ck__sq--dark',
                    isSelected && 'ck__sq--selected',
                    dest && 'ck__sq--dest',
                    last.has(sq) && 'ck__sq--last',
                  ]
                    .filter(Boolean)
                    .join(' ')}
                  aria-label={label}
                  aria-pressed={movable.has(sq) ? isSelected : undefined}
                  disabled={!canAct}
                  onClick={() => void tap(sq)}
                >
                  {piece && (
                    <span
                      className={`ck__piece${capturer ? ' ck__piece--must' : ''}`}
                      style={{ background: MATCH_SEAT_COLORS[piece.seat - 1] }}
                      data-testid={`piece-${r}-${c}`}
                    >
                      {piece.king && <span className="ck__king">♛</span>}
                    </span>
                  )}
                  {dest && <span className="ck__dest" aria-hidden="true" />}
                </button>
              )
            })}
          </div>
        </div>
      )}
    </SeriesFrame>
  )
}
