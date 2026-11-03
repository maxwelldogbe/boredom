import { useEffect, useMemo, useReducer, useRef, useState, type ReactNode } from 'react'
import { forgetAccount, getAuthToken } from '../lib/account'
import { C } from '../lib/constants'
import { reactionsHidden } from '../lib/reactionsPref'
import { wsUrl } from '../lib/endpoints'
import { countFinishedGame } from '../lib/guestPopup'
import { getProfile, saveProfile, toWireProfile } from '../lib/profileStore'
import { markLeaving, markSeated } from '../lib/roomExit'
import { clearRoomToken, getRoomToken, setRoomToken } from '../lib/roomTokens'
import { GameSocket, RequestError } from '../lib/socket'
import type { GameResult, SeatData } from '../types/protocol'
import { RoomActionsContext, RoomStateContext, type RoomActions } from './context'
import { initialRoomState, roomReducer } from './roomReducer'

let toastId = 0
const REJOIN_BASE_BACKOFF_MS = 500
const REJOIN_MAX_BACKOFF_MS = 10_000

/** The profile for room:create / room:join, plus the access token for a registered profile.
 *  The profile is always sent so an expired token still gets a guest seat. */
function seatPayload() {
  const profile = getProfile()
  if (!profile) throw new RequestError('INVALID_ACTION', 'Set up your profile first.')
  const authToken = profile.type === 'registered' ? getAuthToken() : null
  return { profile: toWireProfile(profile), ...(authToken ? { authToken } : {}) }
}

export const EXPIRED_LOGIN_MESSAGE =
  'Your login has expired, so you joined as a guest. Log in again from your profile.'

/** A guest remembers the avatar each room gives them, so creating an account keeps it. */
function rememberGuestAvatar(data: SeatData) {
  const profile = getProfile()
  const me = data.room.players.find((p) => p.id === data.playerId)
  if (profile?.type === 'guest' && me && me.type === 'guest' && me.avatar) saveProfile({ ...profile, avatar: me.avatar })
}

/** Owns the socket and the room state. Wrap the app once. */
export function RoomProvider({ children, socket: given }: { children: ReactNode; socket?: GameSocket }) {
  const [socket] = useState(() => given ?? new GameSocket({ url: wsUrl() }))
  const [state, dispatch] = useReducer(roomReducer, initialRoomState)
  const roomCode = useRef<string | null>(null)
  const stateRef = useRef(state)

  useEffect(() => {
    stateRef.current = state
    roomCode.current = state.room?.code ?? null
  }, [state])

  const actions = useMemo<RoomActions>(() => {
    const toast: RoomActions['toast'] = (message, tone = 'info') =>
      dispatch({ type: 'toast', toast: { id: ++toastId, message, tone } })
    const seat = (data: SeatData) => {
      if (data.authStatus === 'invalid') {
        forgetAccount()
        toast(EXPIRED_LOGIN_MESSAGE, 'error')
      }
      rememberGuestAvatar(data)
      setRoomToken(data.room.code, data.roomToken)
      markSeated(data.room.code)
      roomCode.current = data.room.code
      dispatch({ type: 'seated', playerId: data.playerId, room: data.room })
      return data.room
    }
    /** An intentional exit: mark it, ask the server, navigate away, then clear the room. */
    const exit = async (type: 'room:leave' | 'solo:quit', to: string, go?: (to: string) => void) => {
      const code = roomCode.current
      if (code) markLeaving(code, to)
      try {
        await socket.request(type, {})
      } catch (err) {
        if (!(err instanceof RequestError) || err.code !== 'NOT_IN_ROOM') throw err
      }
      go?.(to)
      if (code) clearRoomToken(code)
      roomCode.current = null
      dispatch({ type: 'left' })
    }
    return {
      socket,
      toast,
      dismissToast: (id) => dispatch({ type: 'dismissToast', id }),
      async createRoom() {
        const data = await socket.request('room:create', seatPayload())
        return seat(data).code
      },
      async joinRoom(code) {
        const upper = code.toUpperCase()
        const roomToken = getRoomToken(upper) ?? undefined
        const payload = { code: upper, ...seatPayload(), ...(roomToken ? { roomToken } : {}) }
        return seat(await socket.request('room:join', payload))
      },
      peek: (code) => socket.request('room:peek', { code: code.toUpperCase() }),
      async leaveRoom(to = '/', go) {
        await exit('room:leave', to, go)
      },
      async quitGame() {
        await socket.request('game:quit', {})
      },
      async selectGame(gameId, settings) {
        await socket.request('room:selectGame', { gameId, settings })
      },
      async startGame() {
        await socket.request('game:start', {})
      },
      async setReady(ready) {
        await socket.request('room:ready', { ready })
      },
      async react(emoji) {
        await socket.request('room:react', { emoji })
      },
      async playAgain() {
        await socket.request('game:playAgain', {})
      },
      async startSolo(gameId, variant) {
        const authToken = getAuthToken()
        if (!authToken) throw new RequestError('REGISTERED_ONLY', 'Solo games are for registered players.')
        return seat(await socket.request('solo:start', { gameId, variant, authToken })).code
      },
      async soloAgain() {
        await socket.request('solo:again', {})
      },
      async soloQuit(to = '/solo', go) {
        await exit('solo:quit', to, go)
      },
      async setStake(amount) {
        await socket.request('room:setStake', { amount })
      },
      async stakeChoice(join) {
        await socket.request('room:stakeChoice', { join })
      },
      async sendAction(action) {
        await socket.request('game:action', action)
      },
    }
  }, [socket])

  useEffect(() => {
    const offStatus = socket.onStatus((status) => dispatch({ type: 'connection', status }))
    const offPush = socket.onPush((msg) => {
      switch (msg.type) {
        case 'room:state':
          dispatch({ type: 'roomState', room: msg.data })
          break
        case 'game:view':
          dispatch({ type: 'gameView', push: msg.data, receivedAt: Date.now() })
          break
        case 'game:event': {
          dispatch({ type: 'gameEvent', event: msg.data })
          // gameOver only comes with a finished game (completed or forfeit), never host_ended.
          const results = msg.data.kind === 'gameOver' ? (msg.data.data as { results?: GameResult[] }).results : null
          if (results?.some((r) => r.playerId === stateRef.current.playerId) && getProfile()?.type === 'guest') {
            countFinishedGame()
          }
          break
        }
        case 'room:event': {
          const event = msg.data
          const current = stateRef.current
          if (event.kind === 'player_quit' && event.playerId !== current.playerId) {
            const activePlayers = current.room?.players.filter((player) => player.inGame).length ?? 0
            actions.toast(
              activePlayers === 2
                ? `${event.nickname} forfeited. You win!`
                : `${event.nickname} forfeited`,
            )
          }
          if (event.kind === 'game_unselected' && event.data?.reason === 'disabled') {
            actions.toast('That game was turned off, so it was unselected.')
          } else if (event.kind === 'game_unselected' && event.playerId === current.playerId) {
            actions.toast('The game was unselected because a guest became the host.')
          }
          if (event.kind === 'stake_changed' && event.playerId !== current.playerId) {
            const amount = Number(event.data?.amount ?? 0)
            actions.toast(
              amount
                ? `The host set a stake of ${amount} Brag coins. Join or sit this round out.`
                : 'The host removed the stake.',
            )
          }
          if (event.kind === 'ready_reset') {
            actions.toast(
              event.data?.reason === 'settings_changed'
                ? 'The settings changed. Tap Ready again.'
                : 'The host changed the game. Tap Ready again.',
            )
          }
          break
        }
        case 'room:reaction': {
          if (reactionsHidden()) break
          const reaction = msg.data
          dispatch({ type: 'reaction', reaction })
          setTimeout(() => dispatch({ type: 'reactionDone', id: reaction.id }), C.REACTION_DISPLAY_MS)
          break
        }
        case 'error':
          if (msg.data.code === 'NOT_IN_ROOM') {
            roomCode.current = null
            dispatch({ type: 'seatLost', message: msg.data.message })
          }
          break
      }
    })
    // Only a real reconnect re-sends room:join with the stored token (auth:hello goes first, from
    // onConnect). Temporary failures retry with backoff; only ROOM_NOT_FOUND is final (the room
    // route then shows "This room closed"). A lost seat (error push, e.g. signed in elsewhere)
    // is final too, so two tabs never steal the seat back and forth.
    let retryTimer: ReturnType<typeof setTimeout> | null = null
    const rejoin = (code: string, attempt: number) => {
      actions.joinRoom(code).catch((err: unknown) => {
        if (roomCode.current !== code) return
        if (err instanceof RequestError && err.code === 'ROOM_NOT_FOUND') {
          clearRoomToken(code)
          roomCode.current = null
          dispatch({ type: 'left' })
          return
        }
        if (err instanceof RequestError && err.code === 'DISCONNECTED') return // the next open retries
        const delay = Math.min(REJOIN_MAX_BACKOFF_MS, REJOIN_BASE_BACKOFF_MS * 2 ** attempt)
        retryTimer = setTimeout(() => {
          if (roomCode.current === code && socket.status === 'connected') rejoin(code, attempt + 1)
        }, delay)
      })
    }
    const offOpen = socket.onOpen((isReconnect) => {
      const code = roomCode.current
      if (!isReconnect || !code || !getRoomToken(code)) return
      if (retryTimer) clearTimeout(retryTimer)
      rejoin(code, 0)
    })
    dispatch({ type: 'connection', status: socket.status })
    socket.connect()
    return () => {
      offStatus()
      offPush()
      offOpen()
      if (retryTimer) clearTimeout(retryTimer)
      socket.close()
    }
  }, [socket, actions])

  return (
    <RoomActionsContext.Provider value={actions}>
      <RoomStateContext.Provider value={state}>{children}</RoomStateContext.Provider>
    </RoomActionsContext.Provider>
  )
}
