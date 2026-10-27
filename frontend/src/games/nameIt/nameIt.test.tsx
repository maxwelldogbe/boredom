import { act, fireEvent, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { FakeWebSocket } from '../../test/fakeWebSocket'
import { nameItFx, type ViewFixture } from '../../test/fixtures'
import { renderWithRoom } from '../../test/render'
import { NameItGame } from './NameItGame'

beforeEach(() => FakeWebSocket.reset())
afterEach(() => vi.useRealTimers())

function props<F extends ViewFixture>(fx: F) {
  const send = vi.fn(async () => true)
  return { view: fx.push.view as F['push']['view'], me: fx.me, room: fx.room, send }
}

describe('NameItGame (real backend views)', () => {
  it('topic chooser: suggestions and a typed topic both send chooseTopic', async () => {
    const fx = nameItFx.topicChooser
    const p = props(fx)
    renderWithRoom(<NameItGame {...p} />)
    const section = screen.getByRole('region', { name: 'Choose a topic' })
    const first = fx.push.view.suggestions[0]
    expect(within(section).getAllByRole('button')).toHaveLength(fx.push.view.suggestions.length + 1)
    await act(async () => fireEvent.click(screen.getByRole('button', { name: first })))
    expect(p.send).toHaveBeenCalledWith({ type: 'chooseTopic', topic: first })
  })

  it('typed topic', async () => {
    const p = props(nameItFx.topicChooser)
    renderWithRoom(<NameItGame {...p} />)
    fireEvent.change(screen.getByLabelText('Or type your own'), { target: { value: '  Cheeses ' } })
    await act(async () => fireEvent.click(screen.getByRole('button', { name: 'Use this topic' })))
    expect(p.send).toHaveBeenCalledWith({ type: 'chooseTopic', topic: 'Cheeses' })
  })

  it('others wait while the topic is chosen', () => {
    const fx = nameItFx.topicWaiting
    renderWithRoom(<NameItGame {...props(fx)} />)
    expect(screen.getByText(/to choose a topic/)).toBeInTheDocument()
    expect(screen.queryByRole('region', { name: 'Choose a topic' })).not.toBeInTheDocument()
  })

  it('my turn: answer input submits on Enter', async () => {
    const fx = nameItFx.myTurn
    const p = props(fx)
    renderWithRoom(<NameItGame {...p} />)
    expect(screen.getByText(fx.push.view.topic!)).toBeInTheDocument()
    const input = screen.getByLabelText('Your answer')
    expect(input).toHaveFocus()
    fireEvent.change(input, { target: { value: ' Apple ' } })
    await act(async () => fireEvent.submit(input.closest('form')!))
    expect(p.send).toHaveBeenCalledWith({ type: 'submitAnswer', text: 'Apple' })
  })

  it('the current player card is highlighted; no turn text', () => {
    for (const fx of [nameItFx.myTurn, nameItFx.canChallenge]) {
      const { unmount } = renderWithRoom(<NameItGame {...props(fx)} />)
      const current = fx.room.players.find((pl) => pl.id === fx.push.view.currentPlayerId)!
      const active = within(screen.getByRole('list', { name: 'Players' }))
        .getAllByRole('listitem')
        .filter((li) => li.classList.contains('player-card--active'))
      expect(active).toHaveLength(1)
      expect(within(active[0]).getByText(current.nickname)).toBeInTheDocument()
      expect(screen.queryByText(/turn|is answering/i)).not.toBeInTheDocument()
      unmount()
    }
  })

  it('challenge button shows only inside the window', async () => {
    const fx = nameItFx.canChallenge
    const until = fx.push.view.challengeWindow!.until
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(until - 2000)
    const p = props(fx)
    const { unmount } = renderWithRoom(<NameItGame {...p} />)
    await act(async () => fireEvent.click(screen.getByRole('button', { name: /Challenge “Car”/ })))
    expect(p.send).toHaveBeenCalledWith({ type: 'challenge' })
    unmount()
    vi.setSystemTime(until + 1)
    renderWithRoom(<NameItGame {...props(fx)} />)
    expect(screen.queryByRole('button', { name: /Challenge/ })).not.toBeInTheDocument()
  })

  it('voter: Valid / Invalid buttons; the timer is paused', async () => {
    const p = props(nameItFx.challengeVoter)
    renderWithRoom(<NameItGame {...p} />)
    expect(screen.getByText('⏸ Paused for a challenge')).toBeInTheDocument()
    await act(async () => fireEvent.click(screen.getByRole('button', { name: '✗ Invalid' })))
    expect(p.send).toHaveBeenCalledWith({ type: 'vote', valid: false })
  })

  it('challenger: no vote buttons, only the count', () => {
    renderWithRoom(<NameItGame {...props(nameItFx.challengeChallenger)} />)
    expect(screen.queryByRole('button', { name: '✓ Valid' })).not.toBeInTheDocument()
    expect(screen.getByText(/Votes in: 0\/1/)).toBeInTheDocument()
  })

  it('eliminated chooser: banner says why, and they pick the next topic', () => {
    renderWithRoom(<NameItGame {...props(nameItFx.eliminatedChooser)} />)
    expect(screen.getByText(/lost a challenge \(“Car”\) and you are out\./)).toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'Choose a topic' })).toBeInTheDocument()
    expect(screen.getAllByText('✖ out')).toHaveLength(1)
  })

  it('done', () => {
    renderWithRoom(<NameItGame {...props(nameItFx.done)} />)
    expect(screen.getByText(/Last one standing/)).toBeInTheDocument()
    expect(screen.getByText(/repeated an answer/)).toBeInTheDocument()
  })
})
