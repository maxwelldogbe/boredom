import { render, screen, within } from '@testing-library/react'
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { SEAT_COLORS, SEAT_ON_COLORS } from '../lib/seatColors'
import { roomFx } from '../test/fixtures'
import type { RoomPublic } from '../types/protocol'
import { PlayerCards } from './PlayerCards'

const NAMES = ['Ann', 'Bob', 'Cat', 'Dan', 'Eve', 'Fay', 'Gus', 'Hal', 'Ivy', 'Jo']

function roomOf(n: number): RoomPublic {
  const base = roomFx.roomLobby2
  const players = NAMES.slice(0, n).map((nickname, i) => ({ ...base.players[0], id: `p${i + 1}`, nickname, online: true }))
  return { ...base, players, hostId: 'p1' }
}

const cards = () => within(screen.getByRole('list', { name: 'Players' })).getAllByRole('listitem')
const ring = (card: HTMLElement) => card.querySelector('.player-card__ring') as HTMLElement
const hex = (rgb: string) => '#' + (rgb.match(/\d+/g) ?? []).slice(0, 3).map((n) => Number(n).toString(16).padStart(2, '0').toUpperCase()).join('')

describe('PlayerCards', () => {
  it('ten distinct seat colours, each with a readable text colour', () => {
    expect(new Set(SEAT_COLORS).size).toBe(10)
    expect(SEAT_COLORS.slice(0, 4)).toEqual(['#FF0000', '#0057FF', '#00C21A', '#FFD500'])
    expect(SEAT_ON_COLORS.slice(0, 4)).toEqual(['#FFFFFF', '#FFFFFF', '#1A1A1A', '#1A1A1A'])
    expect(SEAT_ON_COLORS).toHaveLength(10)
  })

  it.each([2, 3, 4, 6, 10])('%i players: one active card in its seat colour, the rest neutral with a seat ring', (n) => {
    const room = roomOf(n)
    const entries = room.players.map((p) => ({ id: p.id, value: 3 }))
    for (const active of room.players) {
      const { unmount } = render(<PlayerCards room={room} me="p1" entries={entries} activeId={active.id} />)
      const list = cards()
      expect(list).toHaveLength(n)
      list.forEach((card, seat) => {
        expect(within(card).getByText(NAMES[seat])).toBeInTheDocument()
        expect((card.querySelector('.chip__avatar') as HTMLElement).style.background).toBe('var(--border)')
        if (room.players[seat].id === active.id) {
          expect(card).toHaveClass('player-card--active')
          expect(hex(card.style.background)).toBe(SEAT_COLORS[seat])
          expect(card.style.transform).toBe('scale(1.04)')
          expect(hex(card.style.color)).toBe(SEAT_ON_COLORS[seat])
          expect(hex(ring(card).style.borderColor)).toBe('#FFFFFF')
        } else {
          expect(card.getAttribute('style')).toBeNull()
          expect(hex(ring(card).style.borderColor)).toBe(SEAT_COLORS[seat])
          const styled = [...card.querySelectorAll<HTMLElement>('[style]')].filter((el) => el !== ring(card) && !el.classList.contains('chip__avatar'))
          expect(styled).toHaveLength(0)
        }
      })
      expect(list.filter((c) => c.classList.contains('player-card--active'))).toHaveLength(1)
      unmount()
    }
  })

  it('no active card when there is no turn', () => {
    const room = roomOf(3)
    render(<PlayerCards room={room} me="p1" entries={room.players.map((p) => ({ id: p.id }))} />)
    expect(cards().some((c) => c.classList.contains('player-card--active'))).toBe(false)
    expect(document.querySelector('.player-card__value')).toBeNull()
  })

  it('shows You, notes and offline under the name; the value has its label', () => {
    const room = roomOf(3)
    room.players[1] = { ...room.players[1], online: false }
    render(
      <PlayerCards
        room={room}
        me="p1"
        entries={[{ id: 'p1', notes: ['👑 host'] }, { id: 'p2', value: 2, valueLabel: '2 dice' }, { id: 'p3', notes: ['✖ out'] }]}
      />,
    )
    expect(within(cards()[0]).getByText('You')).toBeInTheDocument()
    expect(within(cards()[0]).getByText('👑 host')).toBeInTheDocument()
    expect(within(cards()[1]).getByText('offline')).toBeInTheDocument()
    expect(within(cards()[1]).getByLabelText('2 dice')).toHaveTextContent('2')
    expect(within(cards()[2]).getByText('✖ out')).toBeInTheDocument()
    expect(screen.getAllByText('offline')).toHaveLength(1)
    expect(screen.getAllByText('You')).toHaveLength(1)
  })

  it('a player who left keeps a neutral card', () => {
    const room = roomOf(2)
    render(<PlayerCards room={room} me="p1" entries={[{ id: 'gone' }]} activeId="gone" />)
    expect(cards()[0].style.background).not.toBe('')
    expect(within(cards()[0]).getByText('Someone')).toBeInTheDocument()
  })

  it('320px: 2 columns, up to 4 on wider screens, never sideways scroll', () => {
    const css = readFileSync('src/styles/components.css', 'utf8')
    expect(css).toMatch(/@media \(max-width: 599px\) \{\s*\.player-cards \{\s*--player-cols: 2;/)
    expect(css).toMatch(/grid-template-columns: repeat\(var\(--player-cols, 2\), minmax\(0, 1fr\)\)/)
    expect(css).not.toMatch(/\.player-card[^{]*\{[^}]*overflow-x/)
    for (const [n, cols] of [[2, 2], [3, 3], [4, 4], [10, 4]]) {
      const room = roomOf(n)
      const { unmount } = render(<PlayerCards room={room} me="p1" entries={room.players.map((p) => ({ id: p.id }))} />)
      expect(screen.getByRole('list', { name: 'Players' })).toHaveClass(`player-cards--cols-${cols}`)
      unmount()
    }
  })
})
