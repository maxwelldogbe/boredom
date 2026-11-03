import { GameIcon } from '../../components/GameIcon'
import { GAME_LIST, gameUi } from '../../games/registry'
import { hasGameInstructions } from '../../games/instructions'
import { Button } from '../../components/Button'
import { friendlyError } from '../../lib/errors'
import { canSeeGame, isRegisteredSeat } from '../../lib/registeredOnly'
import { useRoomActions } from '../../state/context'
import type { RoomPublic } from '../../types/protocol'

/** Host-only game cards and settings for the selected game. Guests never see registered-only games;
 *  nobody sees games staff turned off. */
export function GamePicker({ room, me, onHowToPlay = () => {} }: { room: RoomPublic; me: string; onHowToPlay?: () => void }) {
  const { selectGame, toast } = useRoomActions()
  const selected = gameUi(room.selectedGame)
  const registered = isRegisteredSeat(room, me)
  const off = room.disabledGames ?? []
  const games = GAME_LIST.filter((g) => canSeeGame(g.id, registered) && !off.includes(g.id))

  const choose = (settings: Record<string, unknown>, id = room.selectedGame) => {
    if (!id) return
    selectGame(id, settings).catch((err) => toast(friendlyError(err), 'error'))
  }

  return (
    <section className="stack" aria-labelledby="picker-title">
      <h2 id="picker-title" className="section-title">
        Pick a game
      </h2>
      <div className="game-cards">
        {games.map((g) => (
          <button
            key={g.id}
            type="button"
            className="game-card"
            aria-pressed={room.selectedGame === g.id}
            onClick={() => room.selectedGame !== g.id && choose({}, g.id)}
          >
            <span className="game-card__icon" aria-hidden="true">
              <GameIcon id={g.id} />
            </span>
            <span className="game-card__text">
              <strong>
                {g.name}
                {room.selectedGame === g.id && <span className="visually-hidden"> (selected)</span>}
              </strong>
              <span className="game-card__players">
                {g.minPlayers}–{g.maxPlayers} players
              </span>
              <span className="game-card__desc">{g.description}</span>
            </span>
            {room.selectedGame === g.id && (
              <span className="game-card__check" aria-hidden="true">
                ✓
              </span>
            )}
          </button>
        ))}
      </div>
      {selected && selected.settings.length > 0 && (
        <div className="card stack">
          <h3 className="section-title">{selected.name} settings</h3>
          {selected.settings.map((s) => (
            <label key={s.key} className="field">
              <span className="field__label">{s.label}</span>
              <select
                className="field__input"
                value={String(room.settings?.[s.key] ?? '')}
                onChange={(e) => {
                  const option = s.options.find((o) => String(o.value) === e.target.value)
                  if (option) choose({ ...room.settings, [s.key]: option.value })
                }}
              >
                {s.options.map((o) => (
                  <option key={String(o.value)} value={String(o.value)}>
                    {o.label}
                  </option>
                ))}
              </select>
            </label>
          ))}
        </div>
      )}
      {selected && hasGameInstructions(room.selectedGame) && (
        <Button variant="secondary" onClick={onHowToPlay}>
          How to play
        </Button>
      )}
    </section>
  )
}
