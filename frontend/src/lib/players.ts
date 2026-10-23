import type { Player, RoomPublic } from '../types/protocol'

/** Look up a seated player; falls back to a neutral placeholder for unknown ids. */
export function playerById(room: RoomPublic, id: string | null | undefined): Player {
  const found = room.players.find((p) => p.id === id)
  return (
    found ?? {
      id: id ?? '',
      type: 'guest',
      nickname: 'Someone',
      color: '#607D8B',
      avatar: { style: '', seed: '' }, // not a known style, so the initial is shown
      online: false,
      joinedAt: 0,
    }
  )
}

export function nameOf(room: RoomPublic, id: string | null | undefined, me?: string): string {
  if (id && id === me) return 'You'
  return playerById(room, id).nickname
}
