import { useState } from 'react'
import { TimerBar } from '../../components/TimerBar'
import { C } from '../../lib/constants'
import type { TicTacToeView } from '../../types/views'
import { MATCH_SEAT_COLORS } from '../series/matchColors'
import { SeriesFrame } from '../series/SeriesFrame'
import type { GameUiProps } from '../types'
import './ticTacToe.css'

/** Tic-tac-toe (PROTOCOL.md 7.8): X is seat 1 (red cross), O is seat 2 (blue ring). */
export function TicTacToeGame({ view, send, me, room }: GameUiProps<TicTacToeView>) {
  const [pending, setPending] = useState<number | null>(null)
  const game = view.match?.game ?? null
  const legal = new Set(view.role === 'player' && pending === null ? (game?.legalMoves ?? []) : [])

  const place = async (cell: number) => {
    if (!legal.has(cell)) return
    setPending(cell)
    await send({ type: 'place', cell })
    setPending(null)
  }

  return (
    <SeriesFrame view={view} me={me} room={room} send={send} activeId={game?.turn ?? null}>
      {game && (
        <>
          {game.turn && <TimerBar deadline={game.turnDeadline} totalMs={C.TTT_TURN_MS} label="Turn time left" />}
          <div className="ttt__board" role="group" aria-label="Board">
            {game.board.map((mark, cell) => {
              const winning = game.winningCells?.includes(cell) ?? false
              const last = game.lastMove === cell
              const label = [
                `Row ${Math.floor(cell / 3) + 1}, column ${(cell % 3) + 1}: ${mark ?? 'empty'}`,
                last ? 'last move' : '',
                winning ? 'winning line' : '',
              ]
                .filter(Boolean)
                .join(', ')
              return (
                <button
                  key={cell}
                  type="button"
                  className={`ttt__cell${winning ? ' ttt__cell--win' : ''}${last ? ' ttt__cell--last' : ''}`}
                  aria-label={label}
                  disabled={!legal.has(cell)}
                  onClick={() => void place(cell)}
                >
                  {mark && <Mark mark={mark} />}
                </button>
              )
            })}
          </div>
        </>
      )}
    </SeriesFrame>
  )
}

function Mark({ mark }: { mark: 'X' | 'O' }) {
  return (
    <svg className="ttt__mark" viewBox="0 0 40 40" aria-hidden="true">
      {mark === 'X' ? (
        <g stroke={MATCH_SEAT_COLORS[0]} strokeWidth={6} strokeLinecap="round">
          <line x1={8} y1={8} x2={32} y2={32} />
          <line x1={32} y1={8} x2={8} y2={32} />
        </g>
      ) : (
        <circle cx={20} cy={20} r={12} fill="none" stroke={MATCH_SEAT_COLORS[1]} strokeWidth={6} />
      )}
    </svg>
  )
}
