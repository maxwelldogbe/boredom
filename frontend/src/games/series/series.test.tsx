import { act, fireEvent, screen, within } from '@testing-library/react'
import { readFileSync } from 'node:fs'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { AppRoutes } from '../../App'
import { C } from '../../lib/constants'
import { clearMemoryStorage } from '../../lib/storage'
import { FakeWebSocket } from '../../test/fakeWebSocket'
import { connectFourFx, roomFx, ticTacToeFx, type ViewFixture } from '../../test/fixtures'
import { renderWithRoom, saveTestProfile } from '../../test/render'
import { ConnectFourGame } from '../connectFour/ConnectFourGame'
import { connectFourInstructions } from '../instructions/connectFour'
import { ticTacToeInstructions } from '../instructions/ticTacToe'
import { TicTacToeGame } from '../ticTacToe/TicTacToeGame'

beforeEach(() => FakeWebSocket.reset())
afterEach(() => {
  localStorage.clear()
  clearMemoryStorage()
})

function props<F extends ViewFixture>(fx: F) {
  const send = vi.fn(async () => true)
  return { view: fx.push.view as F['push']['view'], me: fx.me, room: fx.room, send }
}

const cells = () => within(screen.getByRole('group', { name: 'Board' })).getAllByRole('button')
const hex = (el: HTMLElement | undefined) =>
  '#' + (el!.style.background.match(/\d+/g) ?? []).slice(0, 3).map((n) => Number(n).toString(16).padStart(2, '0').toUpperCase()).join('')
const nick = (fx: ViewFixture, id: string | null | undefined) => fx.room.players.find((p) => p.id === id)!.nickname

describe('Tic-tac-toe (real backend views)', () => {
  it('my turn: empty cells are buttons, taken ones are not; tapping sends place', async () => {
    const p = props(ticTacToeFx.myTurn)
    renderWithRoom(<TicTacToeGame {...p} />)
    expect(cells()).toHaveLength(9)
    expect(cells().filter((c) => !c.hasAttribute('disabled'))).toHaveLength(7)
    expect(screen.getByRole('button', { name: 'Row 2, column 2: X' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Row 1, column 1: O, last move' })).toBeDisabled()
    await act(async () => fireEvent.click(screen.getByRole('button', { name: 'Row 3, column 3: empty' })))
    expect(p.send).toHaveBeenCalledWith({ type: 'place', cell: 8 })
  })

  it("opponent's turn: nothing to tap, their card is highlighted, no turn text", () => {
    const fx = ticTacToeFx.othersTurn
    const { container } = renderWithRoom(<TicTacToeGame {...props(fx)} />)
    expect(cells().every((c) => c.hasAttribute('disabled'))).toBe(true)
    const active = within(screen.getByRole('list', { name: 'Match players' })).getAllByRole('listitem').find((li) => li.getAttribute('aria-current'))
    expect(active).toHaveTextContent(nick(fx, fx.push.view.match!.game.turn))
    expect(hex(active)).toBe('#FF0000')
    expect(container.textContent).not.toMatch(/your turn/i)
  })

  it('series line shows the game number and games won; avatars and scores on both cards', () => {
    const fx = ticTacToeFx.afterWin
    renderWithRoom(<TicTacToeGame {...props(fx)} />)
    const match = fx.push.view.match!
    expect(screen.getByText('Game 2 of 3')).toBeInTheDocument()
    expect(screen.getByText(`You 1 – 0 ${nick(fx, match.b)}`)).toBeInTheDocument()
    expect(screen.getByText('Last game: You won.')).toBeInTheDocument()
    const cards = within(screen.getByRole('list', { name: 'Match players' })).getAllByRole('listitem')
    expect(cards).toHaveLength(2)
    cards.forEach((card) => expect(card.querySelector('.chip__avatar')).toBeTruthy())
    expect(screen.getByLabelText('1 game won')).toBeInTheDocument()
    expect(screen.getByLabelText('0 games won')).toBeInTheDocument()
  })

  it('done: the winning line is marked and the champion is named', () => {
    const fx = ticTacToeFx.done
    renderWithRoom(<TicTacToeGame {...props(fx)} />)
    expect(cells().filter((c) => /winning line/.test(c.getAttribute('aria-label')!))).toHaveLength(3)
    expect(screen.getByText(/🏆 You win!/)).toBeInTheDocument()
    expect(screen.queryByRole('timer')).not.toBeInTheDocument()
  })

  it('coin flip after 3 draws is announced', () => {
    renderWithRoom(<TicTacToeGame {...props(ticTacToeFx.coinFlip)} />)
    expect(screen.getByText(`🪙 Decided by coin flip after ${C.MATCH_MAX_DRAWS} draws`)).toBeInTheDocument()
  })

  it('spectator: watch banner, switch control sends watch, bracket marks the shown match', async () => {
    const fx = ticTacToeFx.spectator
    const p = props(fx)
    renderWithRoom(<TicTacToeGame {...p} />)
    const [shown, other] = fx.push.view.matches
    expect(screen.getByText(`👀 Watching ${nick(fx, shown.a)} vs ${nick(fx, shown.b)}`)).toBeInTheDocument()
    expect(cells().every((c) => c.hasAttribute('disabled'))).toBe(true)
    await act(async () => fireEvent.click(screen.getByRole('button', { name: `Watch ${nick(fx, other.a)} vs ${nick(fx, other.b)}` })))
    expect(p.send).toHaveBeenCalledWith({ type: 'watch', matchId: other.id })
    const bracket = within(screen.getByRole('list', { name: 'Bracket, round 1' })).getAllByRole('listitem')
    expect(bracket).toHaveLength(3)
    expect(bracket[0]).toHaveAttribute('aria-current', 'true')
    expect(bracket[2]).toHaveTextContent('bye')
  })
})

describe('Connect four (real backend views)', () => {
  it('my turn: seven column buttons; tapping drops; discs are red and ringed blue', async () => {
    const p = props(connectFourFx.myTurn)
    renderWithRoom(<ConnectFourGame {...p} />)
    expect(cells()).toHaveLength(7)
    expect(screen.getByRole('button', { name: 'Column 4: red, blue' })).toBeEnabled()
    await act(async () => fireEvent.click(screen.getByRole('button', { name: 'Column 1: empty' })))
    expect(p.send).toHaveBeenCalledWith({ type: 'drop', column: 0 })
    expect(hex(screen.getByTestId('disc-5-3'))).toBe('#FF0000')
    expect(screen.getByTestId('disc-4-3')).toHaveClass('c4__cell--seat2')
    expect(hex(screen.getByTestId('disc-4-3'))).toBe('#0057FF')
    expect(screen.getByTestId('disc-5-4')).toHaveClass('c4__cell--last')
  })

  it('done: the winning four is highlighted; spectators cannot drop', () => {
    const { container, unmount } = renderWithRoom(<ConnectFourGame {...props(connectFourFx.done)} />)
    expect(container.querySelectorAll('.c4__cell--win')).toHaveLength(4)
    expect(screen.getByText(/Four in a row!/)).toBeInTheDocument()
    unmount()
    renderWithRoom(<ConnectFourGame {...props(connectFourFx.spectator)} />)
    expect(cells().every((c) => c.hasAttribute('disabled'))).toBe(true)
    expect(screen.getByText(/👀 Watching/)).toBeInTheDocument()
  })
})

describe('Room screen around a series game', () => {
  async function mount(fx: ViewFixture) {
    saveTestProfile()
    localStorage.setItem('partypack.roomTokens', JSON.stringify({ [fx.room.code]: 'tok' }))
    const r = renderWithRoom(<AppRoutes />, { route: `/room/${fx.room.code}` })
    await act(async () => r.ws.ack({ ...roomFx.seatAck, room: fx.room, playerId: fx.me, roomToken: 'tok' }))
    await act(async () => r.ws.receive({ type: 'game:view', data: fx.push }))
    return r
  }

  it.each([
    ['tic-tac-toe', ticTacToeFx.bracketPlayer],
    ['connect four', connectFourFx.myTurn],
  ])('%s, active player: cards, Forfeit, reactions and How to play are on screen', async (_, fx) => {
    await mount(fx)
    expect(screen.getByLabelText(`Room ${fx.room.code}`)).toBeInTheDocument()
    expect(screen.getByRole('list', { name: 'Match players' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /🏳️ Forfeit/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Send a reaction' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Menu' }))
    expect(screen.getByRole('button', { name: 'How to play' })).toBeInTheDocument()
  })

  it.each([
    ['tic-tac-toe', ticTacToeFx.spectator],
    ['connect four', connectFourFx.spectator],
  ])('%s, spectator: watch banner and no Forfeit', async (_, fx) => {
    await mount(fx)
    expect(screen.getByText(/👀 Watching/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Forfeit/ })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Leave' })).toBeInTheDocument()
  })
})

describe('Instructions', () => {
  it('take wins needed from the setting and turn time from constants', () => {
    const ttt = JSON.stringify(ticTacToeInstructions({ settings: { bestOf: 5 }, constants: C, playerCount: 2 }))
    expect(ttt).toContain('Get three of your marks in a row.')
    expect(ttt).toContain('The first to win 3 games wins the match.')
    expect(ttt).toContain(`You have ${C.TTT_TURN_MS / 1000} seconds per turn.`)
    const one = JSON.stringify(ticTacToeInstructions({ settings: { bestOf: 1 }, constants: C, playerCount: 2 }))
    expect(one).toContain('The first to win 1 game wins the match.')
    const c4 = JSON.stringify(connectFourInstructions({ settings: { bestOf: 3 }, constants: C, playerCount: 4 }))
    expect(c4).toContain('Connect four of your discs in a row.')
    expect(c4).toContain(`You have ${C.C4_TURN_MS / 1000} seconds per turn.`)
    expect(c4).toContain('everyone else can watch')
  })
})

describe('320px', () => {
  it('boards shrink to fit and never force sideways scroll', () => {
    const ttt = readFileSync('src/games/ticTacToe/ticTacToe.css', 'utf8')
    const c4 = readFileSync('src/games/connectFour/connectFour.css', 'utf8')
    const series = readFileSync('src/games/series/series.css', 'utf8')
    expect(ttt).toMatch(/grid-template-columns: repeat\(3, minmax\(0, 96px\)\)/)
    expect(c4).toMatch(/grid-template-columns: repeat\(7, minmax\(0, 1fr\)\)/)
    expect(c4).toMatch(/@media \(max-width: 359px\)/)
    for (const css of [ttt, c4, series]) {
      expect(css).not.toMatch(/overflow-x/)
      expect(css).not.toMatch(/(?<!max-|min-)width: (3[2-9]\d|[4-9]\d\d)px/)
    }
  })
})
