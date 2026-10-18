/**
 * Opt-in smoke test against a REAL backend on localhost:8000 (skipped otherwise):
 *   LIVE_BACKEND=1 npx vitest run -c vitest.live.config.ts
 * Player A uses the real UI; player B is a bare GameSocket.
 */
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterAll, describe, expect, it } from 'vitest'
import { AppRoutes } from '../App'
import { createProfile, saveProfile, toWireProfile } from '../lib/profileStore'
import { GameSocket } from '../lib/socket'
import { RoomProvider } from '../state/RoomProvider'
import type { PushMessage } from '../types/protocol'
import type { GameViewPush, HangmanView, RpsView } from '../types/views'

const env = (globalThis as { process?: { env: Record<string, string | undefined> } }).process?.env ?? {}
const URL = env.LIVE_WS_URL ?? 'ws://127.0.0.1:8000/ws/'

/** Node's WebSocket sends no Origin header (browsers always do); the backend requires one. */
class OriginWebSocket extends WebSocket {
  constructor(url: string | URL) {
    super(url, { headers: { Origin: 'http://localhost:5173' } } as unknown as string[])
  }
}
const live = () => new GameSocket({ url: URL, WebSocketImpl: OriginWebSocket })
const T = { timeout: 15_000 }

describe.skipIf(!env.LIVE_BACKEND)('live backend smoke test', () => {
  const sockets: GameSocket[] = []
  afterAll(() => sockets.forEach((s) => s.close()))

  function playerB() {
    const socket = live()
    sockets.push(socket)
    const views: GameViewPush[] = []
    socket.onPush((m: PushMessage) => {
      if (m.type === 'game:view') views.push(m.data)
    })
    const latest = <V,>() => views.at(-1)?.view as V
    return { socket, views, latest }
  }

  it('plays RPS, Hangman and starts Guess Race through the real UI', async () => {
    saveProfile(createProfile({ nickname: 'Ann', emoji: '🦊', color: '#3498DB' }))
    const socketA = live()
    sockets.push(socketA)
    render(
      <MemoryRouter>
        <RoomProvider socket={socketA}>
          <AppRoutes />
        </RoomProvider>
      </MemoryRouter>,
    )

    // A creates a room through the UI; B joins with a raw socket.
    fireEvent.click(screen.getByRole('button', { name: 'Create room' }))
    const codeEl = await screen.findByText(/^[A-Z]{4}$/, { selector: '.lobby__code-value' }, T)
    const code = codeEl.textContent!
    const b = playerB()
    const bSeat = await b.socket.request('room:join', {
      code,
      profile: toWireProfile(createProfile({ nickname: 'Bob', emoji: '🐼', color: '#2ECC71' })),
    })
    await screen.findByText('Players (2/10)', {}, T)

    // ---- Rock-Paper-Scissors: A always wins with rock vs scissors ----
    fireEvent.click(screen.getByRole('button', { name: /Rock-Paper-Scissors/ }))
    await waitFor(() => expect(screen.getByRole('button', { name: 'Start game' })).toBeEnabled(), T)
    fireEvent.click(screen.getByRole('button', { name: 'Start game' }))
    for (let round = 1; round <= 2; round++) {
      await screen.findByText('Make your pick', {}, T)
      fireEvent.click(screen.getByRole('button', { name: /Rock/ }))
      await waitFor(() => expect(b.latest<RpsView>()?.phase).toBe('picking'), T)
      await b.socket.request('game:action', { type: 'pick', choice: 'scissors' })
      await screen.findByText(round === 1 ? '✅ You win the round!' : '🏆 You win the match!', {}, T)
    }
    await screen.findByText('Game over', {}, T)
    expect(screen.getByText('+3')).toBeInTheDocument()

    // ---- Hangman: A sets, B solves; then B sets, A loses with wrong letters ----
    fireEvent.click(screen.getByRole('button', { name: 'Back to lobby' }))
    fireEvent.click(await screen.findByRole('button', { name: /Hangman Duel/ }, T))
    await waitFor(() => expect(screen.getByRole('button', { name: 'Start game' })).toBeEnabled(), T)
    fireEvent.click(screen.getByRole('button', { name: 'Start game' }))
    fireEvent.change(await screen.findByLabelText('Secret word', {}, T), { target: { value: 'zebra' } })
    fireEvent.click(screen.getByRole('button', { name: 'Use this word' }))
    await waitFor(() => expect(b.latest<HangmanView>()?.phase).toBe('guessing'), T)
    expect(JSON.stringify(b.latest<HangmanView>())).not.toContain('ZEBRA')
    for (const letter of 'ZEBRA') {
      await b.socket.request('game:action', { type: 'guessLetter', letter })
      await act(async () => new Promise((r) => setTimeout(r, 220))) // stay under the rate limit
    }
    await screen.findByText(/Solved! The word was ZEBRA/, {}, T)
    await waitFor(() => expect(b.latest<HangmanView>()?.isSetter && b.latest<HangmanView>()?.phase === 'setting').toBe(true), T)
    await b.socket.request('game:action', { type: 'setWord', word: 'quiz' })
    const keyboard = await screen.findByLabelText('Letters', {}, T)
    for (const letter of 'ABCDE') {
      fireEvent.click(within(keyboard).getByRole('button', { name: letter }))
      await waitFor(() => expect(within(keyboard).getByRole('button', { name: `${letter}, wrong` })).toBeDisabled(), T)
      await act(async () => new Promise((r) => setTimeout(r, 220))) // human pace, under the rate limit
    }
    fireEvent.click(within(keyboard).getByRole('button', { name: 'F' })) // 6th wrong letter: setter wins
    await screen.findByText(/wins this round! The word was QUIZ/, {}, T)
    await screen.findByText('Game over', {}, T)

    // ---- Guess Race: starts, shows a prompt and accepts a (wrong) guess ----
    fireEvent.click(screen.getByRole('button', { name: 'Back to lobby' }))
    fireEvent.click(await screen.findByRole('button', { name: /Guess Race/ }, T))
    await waitFor(() => expect(screen.getByRole('button', { name: 'Start game' })).toBeEnabled(), T)
    fireEvent.click(screen.getByRole('button', { name: 'Start game' }))
    fireEvent.change(await screen.findByLabelText('Your guess', {}, T), { target: { value: 'definitely not it' } })
    fireEvent.click(screen.getByRole('button', { name: 'Guess' }))
    await screen.findByText(/isn't it/, {}, T)

    expect(bSeat.room.code).toBe(code)
  }, 90_000)
})
