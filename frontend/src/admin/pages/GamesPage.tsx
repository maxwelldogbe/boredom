import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Button } from '../../components/Button'
import { Modal } from '../../components/Modal'
import { useRoomActions } from '../../state/context'
import { AdminApiError, gameAction, type GameRow, type GamesData } from '../api'
import { InlineBar, LoadState, RangeFilter, Refreshing } from '../components'
import { fmtDuration, fmtInt, fmtNum, fmtPct } from '../format'
import { useAdminSession } from '../session'
import { useAdminData } from '../useAdminData'

export default function GamesPage() {
  const [params, setParams] = useSearchParams()
  const range = params.get('range') ?? '7d'
  const { data, error, loading, refreshing, reload } = useAdminData<GamesData>('games', { range })
  const maxPlays = Math.max(0, ...(data?.games.map((g) => g.plays) ?? []))

  return (
    <div className="stack">
      <h1>Games</h1>
      {data && <RangeFilter ranges={data.ranges} value={data.range.key} onChange={(r) => setParams({ range: r })} />}
      {!data && <LoadState error={error} loading={loading} />}
      {data && (
        <Refreshing active={refreshing}>
          <div className="table-scroll card">
            <table className="admin-table">
              <thead>
                <tr>
                  <th scope="col">Game</th>
                  <th scope="col" className="num">Plays</th>
                  <th scope="col" className="num">Unique players</th>
                  <th scope="col" className="num">Avg players</th>
                  <th scope="col" className="num">Avg duration</th>
                  <th scope="col" className="num">Completion</th>
                  <th scope="col" className="num">Abandoned</th>
                  <th scope="col">Players see it</th>
                </tr>
              </thead>
              <tbody>
                {data.games.map((g) => (
                  <tr key={g.id}>
                    <td>
                      <Link to={`/admin/games/${g.id}?range=${data.range.key}`}>{g.name}</Link>
                      {!g.enabled && <span className="badge badge--warn">Off</span>}
                    </td>
                    <td className="num">
                      <span className="bar-cell">
                        <InlineBar value={g.plays} max={maxPlays} />
                        {fmtInt(g.plays)}
                      </span>
                    </td>
                    <td className="num">{fmtInt(g.uniquePlayers)}</td>
                    <td className="num">{fmtNum(g.avgPlayers)}</td>
                    <td className="num">{fmtDuration(g.avgDuration)}</td>
                    <td className="num">{fmtPct(g.completionRate)}</td>
                    <td className="num">{fmtInt(g.abandoned)}</td>
                    <td>
                      {g.known ? (
                        <GameSwitch game={g} canToggle={data.permissions.toggle} onChanged={reload} />
                      ) : (
                        <span className="muted">Retired</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="muted small">
            Plays count completed games. Completion = completed ÷ (completed + abandoned). A game that is off is hidden
            from players and cannot be started; games already running finish normally.
          </p>
        </Refreshing>
      )}
    </div>
  )
}

/** On/off for one game. Turning a game off asks first, since lobbies that picked it lose the pick. */
function GameSwitch({ game, canToggle, onChanged }: { game: GameRow; canToggle: boolean; onChanged: () => void }) {
  const { session, onUnauthorized } = useAdminSession()
  const { toast } = useRoomActions()
  const [busy, setBusy] = useState(false)
  const [confirmOff, setConfirmOff] = useState(false)

  const run = async (action: 'enable' | 'disable') => {
    setBusy(true)
    try {
      await gameAction(game.id, action, session.csrfToken)
      toast(action === 'disable' ? `${game.name} is off. Players can't see it.` : `${game.name} is on again.`)
      onChanged()
    } catch (err) {
      if (err instanceof AdminApiError && err.status === 401) onUnauthorized()
      toast(err instanceof Error ? err.message : 'That did not work.', 'error')
    } finally {
      setBusy(false)
      setConfirmOff(false)
    }
  }

  return (
    <>
      <label className="switch">
        <input
          type="checkbox"
          role="switch"
          checked={game.enabled}
          disabled={!canToggle || busy}
          onChange={() => (game.enabled ? setConfirmOff(true) : run('enable'))}
          aria-label={`${game.name} visible to players`}
        />
        <span>{game.enabled ? 'On' : 'Off'}</span>
      </label>
      {confirmOff && (
        <Modal
          title={`Turn off ${game.name}?`}
          onClose={() => setConfirmOff(false)}
          actions={
            <>
              <Button variant="danger" block disabled={busy} onClick={() => run('disable')}>
                {busy ? 'Turning off…' : 'Yes, turn it off'}
              </Button>
              <Button variant="secondary" block disabled={busy} onClick={() => setConfirmOff(false)}>
                Cancel
              </Button>
            </>
          }
        >
          <p>
            Players will no longer see {game.name} or be able to start it. Lobbies that picked it lose the pick; games
            already running finish normally. You can turn it back on at any time.
          </p>
        </Modal>
      )}
    </>
  )
}
