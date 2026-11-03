import { useCallback } from 'react'
import { Loading } from '../../components/EmptyState'
import { friendlyError } from '../../lib/errors'
import { useRoomActions, useRoomState } from '../../state/context'
import type { ChallengePush } from '../../types/views'
import type { GameAction } from '../types'
import { GuessRun } from './guessRun/GuessRun'
import { HangmanRun } from './hangmanRun/HangmanRun'
import { NameItRun } from './nameItRun/NameItRun'

/** The running solo challenge (PROTOCOL.md 16.1), from the latest game:view. */
export function ChallengeScreen() {
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
  // Challenge views are not in the game registry: the solo room renders them itself.
  const push = game as unknown as ChallengePush | null
  if (!push) return <Loading label="Starting your run…" />
  switch (push.gameId) {
    case 'solo_guess_run':
      return <GuessRun view={push.view} send={send} />
    case 'solo_name_it':
      return <NameItRun view={push.view} send={send} />
    case 'solo_hangman':
      return <HangmanRun view={push.view} send={send} />
    default:
      return <Loading label="Starting your run…" />
  }
}
