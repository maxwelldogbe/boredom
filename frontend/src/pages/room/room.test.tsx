import { act, fireEvent, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { clearMemoryStorage } from '../../lib/storage'
import { FakeWebSocket } from '../../test/fakeWebSocket'
import { roomFx } from '../../test/fixtures'
import { renderWithRoom } from '../../test/render'
import type { RoomPublic } from '../../types/protocol'
import { FinalResults } from './FinalResults'
import { Lobby } from './Lobby'
import { startBlocker } from './startBlocker'
import { TopBar } from './TopBar'

beforeEach(() => FakeWebSocket.reset())
afterEach(() => {
  localStorage.clear()
  clearMemoryStorage()
})

const lobby2 = roomFx.roomLobby2
const host = lobby2.hostId
const guest = lobby2.players.find((p) => p.id !== host)!.id

describe('startBlocker', () => {
  it('explains why Start is disabled', () => {
    expect(startBlocker(lobby2)).toBe('Pick a game first.')
    const solo: RoomPublic = { ...lobby2, players: lobby2.players.slice(0, 1), selectedGame: 'rps' }
    expect(startBlocker(solo)).toBe('Needs at least 2 players.')
    expect(startBlocker({ ...lobby2, selectedGame: 'rps' })).toBeNull()
  })
})

describe('Lobby', () => {
  it('host sees the code, invite options, players, game picker and a disabled Start with a reason', () => {
    renderWithRoom(<Lobby room={lobby2} me={host} />)
    expect(screen.getByText(lobby2.code)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Copy link' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Send on WhatsApp' })).toHaveAttribute('href', expect.stringContaining('wa.me'))
    expect(screen.getByText('Show QR code')).toBeInTheDocument()
    expect(screen.getByText(`Players (2/10)`)).toBeInTheDocument()
    expect(screen.getByText('👑 Host')).toBeInTheDocument()
    expect(within(screen.getByRole('list', { name: 'Players' })).getAllByRole('listitem')).toHaveLength(2)
    expect(screen.getByRole('button', { name: /Rock-Paper-Scissors/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Dots and Boxes/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Liar's Dice/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Name It Survival/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Start game' })).toBeDisabled()
    expect(screen.getByText('Pick a game first.')).toBeInTheDocument()
  })

  it('host picks a game with default settings, then can change a setting and start', () => {
    const { ws, unmount } = renderWithRoom(<Lobby room={lobby2} me={host} />)
    fireEvent.click(screen.getByRole('button', { name: /Guess Race/ }))
    expect(ws.lastFrame()).toMatchObject({ type: 'room:selectGame', payload: { gameId: 'guess_race', settings: {} } })
    const selected: RoomPublic = { ...lobby2, selectedGame: 'guess_race', settings: { content: 'mixed', rounds: 10, difficulty: 'mixed' } }
    unmount()
    renderWithRoom(<Lobby room={selected} me={host} />)
    expect(screen.getByLabelText('Rounds')).toHaveValue('10')
    expect(screen.getByRole('button', { name: 'Start game' })).toBeEnabled()
  })

  it('non-host waits for the host', () => {
    renderWithRoom(<Lobby room={{ ...lobby2, selectedGame: 'rps' }} me={guest} />)
    expect(screen.getByText('⏳ Waiting for the host to start.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Start game' })).not.toBeInTheDocument()
    expect(screen.getByText('Rock-Paper-Scissors')).toBeInTheDocument()
  })

  it('marks offline players with a text label, not color alone', () => {
    const room = roomFx.roomPlayingWithLeaver
    renderWithRoom(<Lobby room={{ ...room, status: 'lobby' }} me={room.hostId} />)
    expect(screen.getByText('offline')).toBeInTheDocument()
  })
})

describe('FinalResults', () => {
  const finished = roomFx.roomFinished

  it('shows the session scoreboard with wins and the leader; host gets Play again / Back to lobby', async () => {
    const { ws } = renderWithRoom(<FinalResults room={finished} me={finished.hostId} />)
    expect(screen.getByText('Session scoreboard')).toBeInTheDocument()
    expect(screen.getByText('1 win')).toBeInTheDocument()
    expect(screen.getByTitle('Session leader')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Play again' }))
    expect(ws.lastFrame().type).toBe('game:playAgain')
    await act(async () => ws.ack({}))
    expect(ws.lastFrame().type).toBe('game:start')
  })

  describe('TopBar forfeit', () => {
    const gameIds = ['rps', 'guess_race', 'hangman', 'dots_and_boxes', 'liars_dice', 'name_it'] as const

    it.each(gameIds)('shows the forfeit button for %s and sends game:quit only after confirmation', (gameId) => {
      const playing = {
        ...roomFx.roomPlayingWithLeaver,
        selectedGame: gameId,
        players: roomFx.roomPlayingWithLeaver.players.map((player) => ({ ...player, inGame: true })),
      }
      const { ws, unmount } = renderWithRoom(
        <TopBar room={playing} me={playing.hostId} onLeaving={() => {}} onLeft={() => {}} />,
      )
      expect(screen.getByRole('button', { name: /Forfeit/ })).toBeInTheDocument()
      fireEvent.click(screen.getByRole('button', { name: /Forfeit/ }))
      expect(screen.getByRole('dialog', { name: 'Forfeit this game?' })).toBeInTheDocument()
      expect(ws.frames().some((frame) => frame.type === 'game:quit')).toBe(false)
      fireEvent.click(screen.getByRole('button', { name: 'Forfeit' }))
      expect(ws.lastFrame()).toMatchObject({ type: 'game:quit', payload: {} })
      unmount()
    })

    it('names the opponent in a two-player confirmation and hides the button after forfeiting', () => {
      const base = roomFx.roomPlayingWithLeaver
      const playing = {
        ...base,
        players: base.players.slice(0, 2).map((player) => ({ ...player, inGame: true })),
      }
      const { ws } = renderWithRoom(
        <TopBar room={playing} me={playing.hostId} onLeaving={() => {}} onLeft={() => {}} />,
      )
      fireEvent.click(screen.getByRole('button', { name: /Forfeit/ }))
      expect(screen.getByText(`${playing.players[1].nickname} will win the game. You'll wait in the room.`)).toBeInTheDocument()
      fireEvent.click(screen.getByRole('button', { name: 'Keep playing' }))
      expect(screen.queryByRole('dialog', { name: 'Forfeit this game?' })).not.toBeInTheDocument()
      expect(ws.frames().some((frame) => frame.type === 'game:quit')).toBe(false)
    })
  })

  it('non-host waits', () => {
    const other = finished.players.find((p) => p.id !== finished.hostId)!.id
    renderWithRoom(<FinalResults room={finished} me={other} />)
    expect(screen.getByText(/Waiting for the host/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Play again' })).not.toBeInTheDocument()
  })
})
