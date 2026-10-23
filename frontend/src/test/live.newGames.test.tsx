/**
 * Opt-in live test for Dots and Boxes, Liar's Dice and Name It Survival (see live.test.tsx).
 * Player A uses the real UI; the others are bare GameSockets.
 */
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterAll, describe, expect, it } from 'vitest'
import { AppRoutes } from '../App'
import { createProfile, saveProfile, toWireProfile } from '../lib/profileStore'
import type { GameSocket } from '../lib/socket'
import { RoomProvider } from '../state/RoomProvider'
import type { DotsView, LiarsDiceView, NameItView } from '../types/views'
import { env, live, pause, socketPlayer, T } from './liveHelpers'

const wait = (ms = 220) => act(async () => pause(ms)) // human pace, under the rate limit

describe.skipIf(!env.LIVE_BACKEND)('live backend: newer games', () => {
  const sockets: GameSocket[] = []
  afterAll(() => sockets.forEach((s) => s.close()))

  async function pickGame(name: RegExp, settings: Record<string, string> = {}) {
    fireEvent.click(await screen.findByRole('button', { name }, T))
    for (const [label, value] of Object.entries(settings)) {
      const select = await screen.findByLabelText(label, {}, T)
      fireEvent.change(select, { target: { value } })
      await waitFor(() => expect(screen.getByLabelText(label)).toHaveValue(value), T)
    }
    await waitFor(() => expect(screen.getByRole('button', { name: 'Start game' })).toBeEnabled(), T)
    fireEvent.click(screen.getByRole('button', { name: 'Start game' }))
  }

  it('plays Dots and Boxes, Liar\'s Dice and Name It Survival through the real UI', async () => {
    saveProfile(createProfile({ nickname: 'Ann', color: '#3498DB' }))
    const socketA = live()
    sockets.push(socketA)
    render(
      <MemoryRouter>
        <RoomProvider socket={socketA}>
          <AppRoutes />
        </RoomProvider>
      </MemoryRouter>,
    )
    fireEvent.click(screen.getByRole('button', { name: 'Create room' }))
    const code = (await screen.findByText(/^[A-Z]{4}$/, { selector: '.lobby__code-value' }, T)).textContent!
    const b = socketPlayer(sockets)
    const bSeat = await b.socket.request('room:join', {
      code,
      profile: toWireProfile(createProfile({ nickname: 'Bob', color: '#2ECC71' })),
    })
    await screen.findByText('Players (2/10)', {}, T)

    // ---- Dots and Boxes 4x4: both players draw the first free line ----
    await pickGame(/Dots and Boxes/, { 'Board size': '4' })
    await waitFor(() => expect(b.latest<DotsView>()?.phase).toBe('playing'), T)
    for (let count = 0; count < 40; count++) {
      await waitFor(() => expect(Object.keys(b.latest<DotsView>().lines)).toHaveLength(count), T)
      const view = b.latest<DotsView>()
      if (view.currentPlayerId === bSeat.playerId) {
        const drawn = Object.keys(view.lines)
        const all = [...Array(5)].flatMap((_, r) => [...Array(4)].map((_, c) => `h:${r}:${c}`))
          .concat([...Array(4)].flatMap((_, r) => [...Array(5)].map((_, c) => `v:${r}:${c}`)))
        await b.socket.request('game:action', { type: 'drawLine', id: all.find((id) => !drawn.includes(id)) })
      } else {
        const board = await screen.findByRole('group', { name: 'Board' }, T)
        const lines = await within(board).findAllByRole('button', {}, T)
        fireEvent.click(lines[0])
      }
      await wait()
    }
    await screen.findByText('Game over', {}, T)

    // ---- Liar's Dice, 3 dice: the opener bids every die as a six, the other calls Liar ----
    fireEvent.click(screen.getByRole('button', { name: 'Back to lobby' }))
    await pickGame(/Liar's Dice/, { 'Starting dice': '3' })
    await screen.findByRole('region', { name: 'Your dice' }, T)
    for (let round = 1; round < 12; round++) {
      await waitFor(() => {
        const v = b.latest<LiarsDiceView>()
        expect(v.phase === 'done' || (v.phase === 'bidding' && v.round === round)).toBe(true)
      }, { timeout: 15_000 })
      if (b.latest<LiarsDiceView>().phase === 'done') break
      for (let step = 0; step < 2; step++) {
        await waitFor(() => expect(b.latest<LiarsDiceView>().history).toHaveLength(step), T)
        const v = b.latest<LiarsDiceView>()
        if (v.isYourTurn) {
          const action = step === 0 ? { type: 'bid', quantity: v.totalDice, face: 6 } : { type: 'callLiar' }
          await b.socket.request('game:action', action)
        } else if (step === 0) {
          for (let q = 1; q < v.totalDice; q++) fireEvent.click(await screen.findByRole('button', { name: 'More dice' }, T))
          fireEvent.click(screen.getByRole('button', { name: 'Face 6' }))
          fireEvent.click(screen.getByRole('button', { name: `Bid ${v.totalDice} × 6s` }))
        } else {
          fireEvent.click(await screen.findByRole('button', { name: 'Liar!' }, T))
        }
        await wait()
        if (step === 1) await screen.findByRole('region', { name: 'Reveal' }, T)
      }
    }
    await screen.findByText('Game over', {}, T)

    // ---- Name It Survival, 3 players: A repeats an answer, then C does ----
    const c = socketPlayer(sockets)
    await c.socket.request('room:join', { code, profile: toWireProfile(createProfile({ nickname: 'Cat', color: '#E74C3C' })) })
    fireEvent.click(screen.getByRole('button', { name: 'Back to lobby' }))
    await screen.findByText('Players (3/10)', {}, T)
    await pickGame(/Name It Survival/)
    let chooser = await screen.findByRole('region', { name: 'Choose a topic' }, T)
    fireEvent.click(within(chooser).getAllByRole('button')[0])
    const answer = async (text: string) => {
      fireEvent.change(await screen.findByLabelText('Your answer', {}, T), { target: { value: text } })
      fireEvent.click(screen.getByRole('button', { name: 'Submit' }))
      await wait()
    }
    await answer('Apple')
    await waitFor(() => expect(b.latest<NameItView>().isYourTurn).toBe(true), T)
    await b.socket.request('game:action', { type: 'submitAnswer', text: 'Pear' })
    await waitFor(() => expect(c.latest<NameItView>().isYourTurn).toBe(true), T)
    await c.socket.request('game:action', { type: 'submitAnswer', text: 'Kiwi' })
    await answer('the apple!')
    await screen.findByText(/repeated an answer \(“the apple!”\) and you are out\./, {}, T)
    chooser = await screen.findByRole('region', { name: 'Choose a topic' }, T)
    fireEvent.click(within(chooser).getAllByRole('button')[0])
    await waitFor(() => expect(b.latest<NameItView>().isYourTurn).toBe(true), T)
    await b.socket.request('game:action', { type: 'submitAnswer', text: 'Blue' })
    await waitFor(() => expect(c.latest<NameItView>().isYourTurn).toBe(true), T)
    await c.socket.request('game:action', { type: 'submitAnswer', text: 'BLUE' })
    await screen.findByText('Game over', {}, T)
  }, 120_000)
})
