import { act, fireEvent, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { AppRoutes } from '../App'
import { getRoomToken } from '../lib/roomTokens'
import { clearMemoryStorage } from '../lib/storage'
import { FakeWebSocket } from '../test/fakeWebSocket'
import { roomFx } from '../test/fixtures'
import { renderWithRoom, saveTestProfile } from '../test/render'

beforeEach(() => FakeWebSocket.reset())
afterEach(() => {
  localStorage.clear()
  clearMemoryStorage()
})

const seat = roomFx.seatAck
const code = seat.room.code

describe('route guard and setup', () => {
  it('sends a visitor without a profile to /setup and back to the invite afterwards', async () => {
    const { ws } = renderWithRoom(<AppRoutes />, { route: `/join/${code}` })
    expect(await screen.findByRole('heading', { name: 'Who are you?' })).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Nickname'), { target: { value: 'Ann' } })
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }))
    expect(await screen.findByText(`Joining room ${code}`)).toBeInTheDocument()
    expect(ws.lastFrame()).toMatchObject({ type: 'room:peek', payload: { code } })
  })

  it('keeps Continue disabled until the nickname is valid', () => {
    renderWithRoom(<AppRoutes />, { route: '/setup' })
    expect(screen.getByRole('button', { name: 'Continue' })).toBeDisabled()
    fireEvent.change(screen.getByLabelText('Nickname'), { target: { value: '<x>' } })
    expect(screen.getByRole('button', { name: 'Continue' })).toBeDisabled()
  })
})

describe('home', () => {
  it('creates a room and enters it', async () => {
    saveTestProfile()
    const { ws } = renderWithRoom(<AppRoutes />)
    fireEvent.click(screen.getByRole('button', { name: 'Create room' }))
    expect(ws.lastFrame().type).toBe('room:create')
    await act(async () => ws.ack(seat))
    expect(await screen.findByText('Tap to copy')).toBeInTheDocument()
    expect(getRoomToken(code)).toBe(seat.roomToken)
  })

  it('shows an inline error for a badly formatted code without calling the server', async () => {
    saveTestProfile()
    const { ws } = renderWithRoom(<AppRoutes />)
    fireEvent.click(screen.getByRole('button', { name: 'Join room' }))
    fireEvent.paste(screen.getByLabelText('Room code letter 1'), { clipboardData: { getData: () => 'ABIO' } })
    fireEvent.click(screen.getByRole('button', { name: 'Join' }))
    expect(screen.getByRole('alert')).toHaveTextContent("That doesn't look like a room code.")
    expect(ws.frames().map((f) => f.type)).toEqual(['guest:quota']) // only the free-games check
  })

  it('shows ROOM_NOT_FOUND inline', async () => {
    saveTestProfile()
    const { ws } = renderWithRoom(<AppRoutes />)
    fireEvent.click(screen.getByRole('button', { name: 'Join room' }))
    fireEvent.paste(screen.getByLabelText('Room code letter 1'), { clipboardData: { getData: () => 'ZZZZ' } })
    fireEvent.click(screen.getByRole('button', { name: 'Join' }))
    await act(async () => ws.nack('ROOM_NOT_FOUND'))
    expect(screen.getByRole('alert')).toHaveTextContent("We couldn't find room ZZZZ")
  })
})

describe('join landing', () => {
  async function landing(reply: (ws: FakeWebSocket) => void) {
    saveTestProfile()
    const r = renderWithRoom(<AppRoutes />, { route: `/join/${code}` })
    await act(async () => reply(r.ws))
    return r
  }

  it('rejects an invalid code format', () => {
    saveTestProfile()
    renderWithRoom(<AppRoutes />, { route: '/join/AB1' })
    expect(screen.getByText("That doesn't look like a room code")).toBeInTheDocument()
  })

  it('shows the host name from room:peek, then joins and enters the room', async () => {
    const { ws } = await landing((ws) => ws.ack(roomFx.peekExists))
    expect(screen.getByText(`Joining ${roomFx.peekExists.hostNickname}'s room`)).toBeInTheDocument()
    expect(ws.lastFrame()).toMatchObject({ type: 'room:join', payload: { code } })
    await act(async () => ws.ack(seat))
    expect(await screen.findByText('Tap to copy')).toBeInTheDocument()
  })

  it('room not found (peek says it does not exist)', async () => {
    await landing((ws) => ws.ack(roomFx.peekMissing))
    expect(screen.getByText(`Room ${code} not found`)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Try another code' })).toBeInTheDocument()
  })

  it('room full', async () => {
    const { ws } = await landing((ws) => ws.ack(roomFx.peekExists))
    await act(async () => ws.nack('ROOM_FULL'))
    expect(screen.getByText('This room is full (10 players).')).toBeInTheDocument()
  })

  it('game in progress offers Retry', async () => {
    const { ws } = await landing((ws) => ws.ack(roomFx.peekExists))
    await act(async () => ws.nack('GAME_IN_PROGRESS'))
    expect(screen.getByText('A game is in progress. You can join when it ends.')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }))
    expect(ws.lastFrame().type).toBe('room:peek')
  })
})

describe('room page', () => {
  it('rejoins with the stored token after a refresh', async () => {
    saveTestProfile()
    localStorage.setItem('partypack.roomTokens', JSON.stringify({ [code]: 'tok' }))
    const { ws } = renderWithRoom(<AppRoutes />, { route: `/room/${code}` })
    expect(screen.getByText(`Joining room ${code}…`)).toBeInTheDocument()
    expect(ws.lastFrame()).toMatchObject({ type: 'room:join', payload: { roomToken: 'tok' } })
    await act(async () => ws.ack(seat))
    expect(await screen.findByText('Tap to copy')).toBeInTheDocument()
  })

  it('without a token goes through the invite landing', async () => {
    saveTestProfile()
    const { ws } = renderWithRoom(<AppRoutes />, { route: `/room/${code}` })
    expect(await screen.findByText(`Joining room ${code}`)).toBeInTheDocument()
    expect(ws.lastFrame().type).toBe('room:peek')
  })

  it('shows a clear message when the seat is lost', async () => {
    saveTestProfile()
    const { ws } = renderWithRoom(<AppRoutes />)
    fireEvent.click(screen.getByRole('button', { name: 'Create room' }))
    await act(async () => ws.ack(seat))
    await act(async () =>
      ws.receive({ type: 'error', data: { code: 'NOT_IN_ROOM', message: 'You joined from another tab.' } }),
    )
    expect(await screen.findByText("You're no longer in this room")).toBeInTheDocument()
    expect(screen.getByText('You joined from another tab.')).toBeInTheDocument()
  })
})
