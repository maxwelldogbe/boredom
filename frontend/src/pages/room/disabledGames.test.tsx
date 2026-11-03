import { screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { GAME_LIST } from '../../games/registry'
import { friendlyError } from '../../lib/errors'
import { RequestError } from '../../lib/socket'
import { registeredOnlyFx } from '../../test/fixtures'
import { renderWithRoom } from '../../test/render'
import { GamePicker } from './GamePicker'

const cards = () => within(screen.getByRole('heading', { name: 'Pick a game' }).parentElement!).getAllByRole('button')

describe('Games staff turned off', () => {
  it('are missing from the picker', () => {
    const { me, room } = registeredOnlyFx.registeredHostEmpty
    renderWithRoom(<GamePicker room={{ ...room, disabledGames: ['rps', 'checkers'] }} me={me} />)
    const names = cards().map((c) => c.querySelector('strong')!.textContent)
    expect(names).toHaveLength(GAME_LIST.length - 2)
    expect(names).not.toContain('Rock-Paper-Scissors')
    expect(names).not.toContain('Checkers')
  })

  it('servers without the list show every game', () => {
    const { me, room } = registeredOnlyFx.registeredHostEmpty
    renderWithRoom(<GamePicker room={{ ...room, disabledGames: undefined }} me={me} />)
    expect(cards()).toHaveLength(GAME_LIST.length)
  })

  it('GAME_DISABLED has a plain message', () => {
    expect(friendlyError(new RequestError('GAME_DISABLED', 'x'))).toBe('This game is turned off right now. Pick another one.')
  })
})
