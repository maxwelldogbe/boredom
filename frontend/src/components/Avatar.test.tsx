import { fireEvent, render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { avatarUrl } from '../lib/avatar'
import { roomFx } from '../test/fixtures'
import { Avatar } from './Avatar'

const player = roomFx.roomLobby2.players[0]

describe('Avatar', () => {
  it('renders the DiceBear image for a real server-assigned avatar', () => {
    const { container } = render(<Avatar avatar={player.avatar} nickname={player.nickname} color={player.color} />)
    const img = container.querySelector('img')
    expect(img?.getAttribute('src')).toBe(avatarUrl(player.avatar))
    expect(img?.getAttribute('src')).toMatch(
      new RegExp(`^https://api\\.dicebear\\.com/10\\.x/${player.avatar.style}/svg\\?seed=${player.avatar.seed}$`),
    )
  })

  it('falls back to the initial when the image fails to load', () => {
    const { container } = render(<Avatar avatar={player.avatar} nickname="sam" color="#E74C3C" />)
    fireEvent.error(container.querySelector('img')!)
    expect(container.querySelector('img')).toBeNull()
    expect(container.textContent).toBe('S')
  })

  it('never builds a URL from an unknown style or a bad seed', () => {
    for (const avatar of [{ style: 'evil', seed: 'x' }, { style: 'cutouts', seed: '../x?y' }, null]) {
      const { container, unmount } = render(<Avatar avatar={avatar} nickname="Ann" color="#E74C3C" />)
      expect(container.querySelector('img')).toBeNull()
      expect(container.textContent).toBe('A')
      unmount()
    }
  })

  it('real room:state players carry avatars and no emoji', () => {
    for (const p of roomFx.roomLobby2.players) {
      expect(p).toHaveProperty('avatar')
      expect(p).not.toHaveProperty('emoji')
    }
  })
})
