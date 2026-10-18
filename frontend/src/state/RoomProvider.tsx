import { useEffect, useMemo, useReducer, useRef, useState, type ReactNode } from 'react'
import { wsUrl } from '../lib/endpoints'
import { getProfile, toWireProfile } from '../lib/profileStore'
import { clearRoomToken, getRoomToken, setRoomToken } from '../lib/roomTokens'
import { GameSocket, RequestError } from '../lib/socket'
import type { RoomPublic } from '../types/protocol'
import { RoomActionsContext, RoomStateContext, type RoomActions } from './context'
import { initialRoomState, roomReducer } from './roomReducer'

let toastId = 0

function requireProfile() {
  const profile = getProfile()
  if (!profile) throw new RequestError('INVALID_ACTION', 'Set up your profile first.')
  return toWireProfile(profile)
}

/** Owns the socket and the room state. Wrap the app once. */
export function RoomProvider({ children, socket: given }: { children: ReactNode; socket?: GameSocket }) {
  const [socket] = useState(() => given ?? new GameSocket({ url: wsUrl() }))
  const [state, dispatch] = useReducer(roomReducer, initialRoomState)
  const roomCode = useRef<string | null>(null)

  useEffect(() => {
    roomCode.current = state.room?.code ?? null
  }, [state.room?.code])

  const actions = useMemo<RoomActions>(() => {
    const seat = (data: { playerId: string; roomToken: string; room: RoomPublic }) => {
      setRoomToken(data.room.code, data.roomToken)
      roomCode.current = data.room.code
      dispatch({ type: 'seated', playerId: data.playerId, room: data.room })
      return data.room
    }
    const toast: RoomActions['toast'] = (message, tone = 'info') =>
      dispatch({ type: 'toast', toast: { id: ++toastId, message, tone } })
    return {
      socket,
      toast,
      dismissToast: (id) => dispatch({ type: 'dismissToast', id }),
      async createRoom() {
        const data = await socket.request('room:create', { profile: requireProfile() })
        return seat(data).code
      },
      async joinRoom(code) {
        const upper = code.toUpperCase()
        const roomToken = getRoomToken(upper) ?? undefined
        const payload = { code: upper, profile: requireProfile(), ...(roomToken ? { roomToken } : {}) }
        return seat(await socket.request('room:join', payload))
      },
      peek: (code) => socket.request('room:peek', { code: code.toUpperCase() }),
      async leaveRoom() {
        const code = roomCode.current
        try {
          await socket.request('room:leave', {})
        } catch (err) {
          if (!(err instanceof RequestError) || err.code !== 'NOT_IN_ROOM') throw err
        }
        if (code) clearRoomToken(code)
        roomCode.current = null
        dispatch({ type: 'left' })
      },
      async selectGame(gameId, settings) {
        await socket.request('room:selectGame', { gameId, settings })
      },
      async startGame() {
        await socket.request('game:start', {})
      },
      async playAgain() {
        await socket.request('game:playAgain', {})
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
        case 'game:event':
          dispatch({ type: 'gameEvent', event: msg.data })
          break
        case 'error':
          if (msg.data.code === 'NOT_IN_ROOM') {
            roomCode.current = null
            dispatch({ type: 'seatLost', message: msg.data.message })
          }
          break
      }
    })
    // Only a real reconnect re-sends room:join with the stored token. A lost seat
    // (error push) is final, so two tabs never steal the seat back and forth.
    const offOpen = socket.onOpen((isReconnect) => {
      const code = roomCode.current
      if (!isReconnect || !code || !getRoomToken(code)) return
      actions.joinRoom(code).catch(() => {
        roomCode.current = null
        dispatch({ type: 'left' })
        actions.toast(`You were disconnected from room ${code}.`, 'error')
      })
    })
    dispatch({ type: 'connection', status: socket.status })
    socket.connect()
    return () => {
      offStatus()
      offPush()
      offOpen()
      socket.close()
    }
  }, [socket, actions])

  return (
    <RoomActionsContext.Provider value={actions}>
      <RoomStateContext.Provider value={state}>{children}</RoomStateContext.Provider>
    </RoomActionsContext.Provider>
  )
}
