import { useCallback, type ComponentType } from 'react'
import { Loading } from '../../components/EmptyState'
import { GAME_UIS } from '../../games/registry'
import type { GameAction, GameUiProps } from '../../games/types'
import { friendlyError } from '../../lib/errors'
import { useRoomActions, useRoomState } from '../../state/context'
import type { RoomPublic } from '../../types/protocol'
import type { GameViewPush } from '../../types/views'

/** Renders the running game's UI from the registry with the latest personal view. */
export function GameScreen({ room, me }: { room: RoomPublic; me: string }) {
  const { game } = useRoomState()
  const { sendAction, toast } = useRoomActions()

  const send = useCallback(
    async (action: GameAction) => {
      try {
        await sendAction(action)
        return true
      } catch (err) {
        toast(friendlyError(err), 'error')
        return false
      }
    },
    [sendAction, toast],
  )

  if (!game) return <Loading label="Starting the game…" />
  return renderGame(game, { send, me, room })
}

type AnyGameComponent = ComponentType<GameUiProps<GameViewPush['view']>>

/** Generic dispatch by gameId, so adding a game never touches this file. */
function renderGame(push: GameViewPush, rest: Omit<GameUiProps<unknown>, 'view'>) {
  const Component = GAME_UIS[push.gameId].Component as AnyGameComponent
  return <Component view={push.view} {...rest} />
}
