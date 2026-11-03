import { useState } from 'react'
import { TimerBar } from '../../components/TimerBar'
import { C } from '../../lib/constants'
import type { ConnectFourView } from '../../types/views'
import { MATCH_SEAT_COLORS } from '../series/matchColors'
import { SeriesFrame } from '../series/SeriesFrame'
import type { GameUiProps } from '../types'
import './connectFour.css'

const COLUMNS = 7
const SEAT_NAMES = ['red', 'blue'] // bottom to top in column labels

/** Connect Four (PROTOCOL.md 7.9): tap a column; seat 1 solid red, seat 2 blue with a white ring. */
export function ConnectFourGame({ view, send, me, room }: GameUiProps<ConnectFourView>) {
  const [pending, setPending] = useState<number | null>(null)
  const game = view.match?.game ?? null
  const legal = new Set(view.role === 'player' && pending === null ? (game?.legalMoves ?? []) : [])
  const winning = new Set((game?.winningCells ?? []).map(([r, c]) => `${r}:${c}`))

  const drop = async (column: number) => {
    if (!legal.has(column)) return
    setPending(column)
    await send({ type: 'drop', column })
    setPending(null)
  }

  return (
    <SeriesFrame view={view} me={me} room={room} send={send} activeId={game?.turn ?? null}>
      {game && (
        <>
          {game.turn && <TimerBar deadline={game.turnDeadline} totalMs={C.C4_TURN_MS} label="Turn time left" />}
          <div className="c4__board" role="group" aria-label="Board">
            {Array.from({ length: COLUMNS }, (_, column) => {
              const full = game.board[0][column] !== null
              const discs = game.board
                .map((row) => row[column])
                .filter((seat) => seat !== null)
                .reverse()
                .map((seat) => SEAT_NAMES[seat - 1])
              return (
                <button
                  key={column}
                  type="button"
                  className="c4__column"
                  aria-label={`Column ${column + 1}: ${discs.length ? discs.join(', ') : 'empty'}${full ? ' (full)' : ''}`}
                  disabled={!legal.has(column)}
                  onClick={() => void drop(column)}
                >
                  {game.board.map((row, r) => {
                    const seat = row[column]
                    const win = winning.has(`${r}:${column}`)
                    const last = game.lastMove?.row === r && game.lastMove.column === column
                    return (
                      <span
                        key={r}
                        className={`c4__cell${seat ? ` c4__cell--seat${seat}` : ''}${win ? ' c4__cell--win' : ''}${last ? ' c4__cell--last' : ''}`}
                        style={seat ? { background: MATCH_SEAT_COLORS[seat - 1] } : undefined}
                        data-testid={seat ? `disc-${r}-${column}` : undefined}
                        aria-hidden="true"
                      />
                    )
                  })}
                </button>
              )
            })}
          </div>
          {(game.lastMove || game.winningCells) && (
            <p className="visually-hidden" role="status">
              {game.lastMove && `Last move: column ${game.lastMove.column + 1}, row ${game.lastMove.row + 1} from the top.`}
              {game.winningCells && ' Four in a row!'}
            </p>
          )}
        </>
      )}
    </SeriesFrame>
  )
}
