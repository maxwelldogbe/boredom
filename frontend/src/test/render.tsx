/** Render helpers: a RoomProvider on a FakeWebSocket plus a MemoryRouter. */
import { act, render } from '@testing-library/react'
import type { ReactElement } from 'react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { createProfile, saveProfile } from '../lib/profileStore'
import { GameSocket } from '../lib/socket'
import { RoomProvider } from '../state/RoomProvider'
import { asWebSocket, FakeWebSocket } from './fakeWebSocket'

export function saveTestProfile(nickname = 'Sam') {
  const profile = createProfile({ nickname, color: '#E74C3C' })
  saveProfile(profile)
  return profile
}

export function renderWithRoom(ui: ReactElement, { route = '/', path = '*' }: { route?: string; path?: string } = {}) {
  const socket = new GameSocket({ url: 'ws://test/ws/', WebSocketImpl: asWebSocket })
  const result = render(
    <MemoryRouter initialEntries={[route]}>
      <RoomProvider socket={socket}>
        <Routes>
          <Route path={path} element={ui} />
          <Route path="*" element={<p>Other page</p>} />
        </Routes>
      </RoomProvider>
    </MemoryRouter>,
  )
  const ws = FakeWebSocket.last()
  act(() => ws.open())
  return { ...result, ws, socket }
}
