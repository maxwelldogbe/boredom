import { act, fireEvent, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { AppRoutes } from '../../App'
import { C } from '../../lib/constants'
import { clearMemoryStorage } from '../../lib/storage'
import { FakeWebSocket } from '../../test/fakeWebSocket'
import { roomFx } from '../../test/fixtures'
import { renderWithRoom, saveTestProfile } from '../../test/render'
import type { RoomPublic, SeatData } from '../../types/protocol'

beforeEach(() => FakeWebSocket.reset())
afterEach(() => {
  localStorage.clear()
  clearMemoryStorage()
})

const host = roomFx.roomLobby2.hostId
const guest = roomFx.roomLobby2.players.find((p) => p.id !== host)!.id

function lobbyWith(game: RoomPublic['selectedGame'], settings: Record<string, unknown>): RoomPublic {
  return {
    ...roomFx.roomLobby2,
    selectedGame: game,
    settings,
  }
}

function seatFor(room: RoomPublic, playerId: string): SeatData {
  return { ...roomFx.seatAck, room, playerId, roomToken: 'tok' }
}

async function mountRoom(room: RoomPublic, playerId = host) {
  saveTestProfile()
  localStorage.setItem('partypack.roomTokens', JSON.stringify({ [room.code]: 'tok' }))
  const render = renderWithRoom(<AppRoutes />, { route: `/room/${room.code}` })
  expect(render.ws.lastFrame()).toMatchObject({ type: 'room:join', payload: { code: room.code, roomToken: 'tok' } })
  await act(async () => render.ws.ack(seatFor(room, playerId)))
  await screen.findByText('Tap to copy')
  return render
}

describe('How to play modal', () => {
  it('supports Close (X), Escape and non-closing backdrop, and sends no message', async () => {
    const rpsRoom = lobbyWith('rps', { bestOf: 3, mode: 'duel' })
    const { ws } = await mountRoom(rpsRoom, guest)

    expect(await screen.findByRole('dialog')).toBeInTheDocument()
    const close = screen.getByRole('button', { name: 'Close' })
    expect(close).toHaveStyle({ minWidth: '44px', minHeight: '44px' })
    const beforeClose = ws.sent.length
    fireEvent.click(close)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(ws.sent).toHaveLength(beforeClose)

    const trigger = screen.getByRole('button', { name: 'How to play' })
    trigger.focus()
    fireEvent.click(trigger)
    const dialog = screen.getByRole('dialog')
    expect(dialog).toBeInTheDocument()
    expect(dialog.querySelector('.modal__header')).toBeTruthy()
    expect(dialog.querySelector('.modal__body')).toBeTruthy()
    expect(dialog.querySelector('.modal__actions')).toBeTruthy()
    const closeAgain = screen.getByRole('button', { name: 'Close' })
    expect(closeAgain).toHaveFocus()
    fireEvent.keyDown(document, { key: 'Tab', shiftKey: true })
    expect(screen.getByRole('button', { name: 'Continue' })).toHaveFocus()
    fireEvent.keyDown(document, { key: 'Tab' })
    expect(screen.getByRole('button', { name: 'Close' })).toHaveFocus()
    const modal = document.querySelector('.modal')
    expect(modal).toBeTruthy()
    fireEvent.mouseDown(modal as Element)
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(trigger).toHaveFocus()
  })

  it('renders Guess Race content for scramble, emoji and mixed, and updates live while open', async () => {
    const scrambleRoom = lobbyWith('guess_race', { content: 'scramble', rounds: 5, difficulty: 'mixed' })
    const { ws } = await mountRoom(scrambleRoom, guest)

    expect(await screen.findByRole('dialog')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /guess race/i })).toBeInTheDocument()
    expect(screen.getByText('Unscramble the letters to find the hidden word before everyone else.')).toBeInTheDocument()
    expect(screen.getAllByText((_, el) => Boolean(el?.textContent?.includes('PLEPA = APPLE')))).not.toHaveLength(0)
    expect(screen.getByText(`You have ${C.GUESS_ROUND_MS / 1000} seconds for each puzzle.`)).toBeInTheDocument()
    expect(screen.getByText(new RegExp(`first to solve earns ${C.GUESS_RANK_POINTS_FIRST} points`, 'i'))).toBeInTheDocument()
    expect(screen.getByText(new RegExp(`second earns ${C.GUESS_RANK_POINTS_FIRST - C.GUESS_RANK_POINTS_STEP}`, 'i'))).toBeInTheDocument()
    expect(screen.queryByText(/third earns/i)).not.toBeInTheDocument()
    expect(screen.getByText('After 5 puzzles, the player with the most points wins.')).toBeInTheDocument()
    const openDialog = screen.getByRole('dialog')

    act(() =>
      ws.receive({
        type: 'room:state',
        data: lobbyWith('guess_race', { content: 'emoji', rounds: 10, difficulty: 'mixed' }),
      }),
    )
    expect(screen.getByRole('dialog')).toBe(openDialog)
    expect(screen.getByText('Work out the word or title hidden in the emojis before everyone else.')).toBeInTheDocument()
    expect(screen.getAllByText((_, el) => Boolean(el?.textContent?.includes('🌧️🏹 = Rainbow')))).not.toHaveLength(0)
    expect(screen.getAllByText((_, el) => Boolean(el?.textContent?.includes('🦁👑 = The Lion King')))).not.toHaveLength(0)
    expect(screen.getByText('Starting with "The" is optional.')).toBeInTheDocument()
    expect(screen.getByText('After 10 puzzles, the player with the most points wins.')).toBeInTheDocument()

    act(() =>
      ws.receive({
        type: 'room:state',
        data: lobbyWith('guess_race', { content: 'mixed', rounds: 15, difficulty: 'mixed' }),
      }),
    )
    expect(
      screen.getByText('Solve each puzzle before everyone else. Some are scrambled words and some are emoji puzzles.'),
    ).toBeInTheDocument()
    expect(
      screen.getByText(
        `Clues appear as time passes. After ${C.GUESS_HINT1_MS / 1000} seconds you get a clue: the category for emoji puzzles, or the number of letters for scrambled words. After ${C.GUESS_HINT2_MS / 1000} seconds you also see the first letter.`,
      ),
    ).toBeInTheDocument()
    expect(screen.getByText('After 15 puzzles, the player with the most points wins.')).toBeInTheDocument()
  })

  it('opens on selection, closes on Continue/playing, and reopens from lobby + in-game menu', async () => {
    const base = lobbyWith(null, {})
    const { ws } = await mountRoom(base, guest)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()

    const selected = lobbyWith('guess_race', { content: 'mixed', rounds: 10, difficulty: 'mixed' })
    act(() => ws.receive({ type: 'room:state', data: selected }))
    expect(await screen.findByRole('dialog')).toBeInTheDocument()

    const sentBeforeContinue = ws.sent.length
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(ws.sent).toHaveLength(sentBeforeContinue)

    fireEvent.click(screen.getByRole('button', { name: 'How to play' }))
    expect(screen.getByRole('dialog')).toBeInTheDocument()

    const playing = { ...selected, status: 'playing' as const }
    act(() => ws.receive({ type: 'room:state', data: playing }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Menu' }))
    fireEvent.click(screen.getByRole('button', { name: 'How to play' }))
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(screen.getByText(/the game keeps running/i)).toBeInTheDocument()
  })

  it('opens once when joining a lobby with Guess Race already selected', async () => {
    const selected = lobbyWith('guess_race', { content: 'mixed', rounds: 10, difficulty: 'mixed' })
    const { ws } = await mountRoom(selected, guest)
    expect(await screen.findByRole('dialog')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    act(() => ws.receive({ type: 'room:state', data: selected }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('renders Hangman instructions for each mode and updates the challenge live', async () => {
    const hangmanRoom = lobbyWith('hangman', { mode: 'group' })
    const { ws } = await mountRoom(hangmanRoom)

    expect(await screen.findByRole('dialog')).toBeInTheDocument()
    expect(screen.getByText('Work together to guess the secret word before the drawing is complete.')).toBeInTheDocument()
    expect(screen.getByText('Everyone else picks letters. You all share the same guesses, so work together.')).toBeInTheDocument()
    expect(screen.getByText(`Every round is worth ${C.HANGMAN_POT} points, whatever the word is.`)).toBeInTheDocument()
    expect(
      screen.getByText(
        `Example: the word is guessed after 2 wrong guesses. Guessers get ${C.HANGMAN_POT - 2 * C.HANGMAN_WRONG_COST}, and the setter gets ${2 * C.HANGMAN_WRONG_COST}.`,
      ),
    ).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Not-a-real-word' })).not.toBeInTheDocument()

    const duelRoom = lobbyWith('hangman', { mode: 'duel' })
    act(() => ws.receive({ type: 'room:state', data: duelRoom }))
    expect(screen.getByText("Guess your opponent's secret word before the drawing is complete.")).toBeInTheDocument()
    expect(screen.getByText('The other player picks letters one at a time.')).toBeInTheDocument()
    expect(screen.queryByText('The guessers\' points are shared equally.')).not.toBeInTheDocument()

    const groupRoomWithFlagging = {
      ...hangmanRoom,
      players: [...hangmanRoom.players, { ...hangmanRoom.players[0], id: 'p_third', nickname: 'Pat' }],
    }
    act(() => ws.receive({ type: 'room:state', data: groupRoomWithFlagging }))
    expect(screen.getByRole('heading', { name: 'Not-a-real-word' })).toBeInTheDocument()
    expect(
      screen.getByText(
        `Think the setter used a made-up word? After the round, you have ${C.HANGMAN_FLAG_WINDOW_MS / 1000} seconds to flag it.`,
      ),
    ).toBeInTheDocument()

    act(() => ws.receive({ type: 'room:state', data: hangmanRoom }))
    expect(screen.queryByRole('heading', { name: 'Not-a-real-word' })).not.toBeInTheDocument()
  })
})
