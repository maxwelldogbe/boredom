import type { RoomPublic } from '../types/protocol'

/** Fixed colour per seat (room join order), the same on every screen. Profile colours are not used. */
export const SEAT_COLORS = [
  '#FF0000',
  '#0057FF',
  '#00C21A',
  '#FFD500',
  '#FF7A00',
  '#8A2BE2',
  '#FF2D95',
  '#00B3B3',
  '#8B4513',
  '#6B6B6B',
] as const

/** Readable text on each seat colour when it fills the active player card. */
export const SEAT_ON_COLORS = [
  '#FFFFFF',
  '#FFFFFF',
  '#1A1A1A',
  '#1A1A1A',
  '#1A1A1A',
  '#FFFFFF',
  '#1A1A1A',
  '#1A1A1A',
  '#FFFFFF',
  '#FFFFFF',
] as const

// For ids no longer seated in the room.
const NO_SEAT = { color: '#607D8B', on: '#FFFFFF' }

export function seatColor(room: RoomPublic, id: string): string {
  const seat = room.players.findIndex((p) => p.id === id)
  return seat >= 0 ? SEAT_COLORS[seat % SEAT_COLORS.length] : NO_SEAT.color
}

export function onSeatColor(room: RoomPublic, id: string): string {
  const seat = room.players.findIndex((p) => p.id === id)
  return seat >= 0 ? SEAT_ON_COLORS[seat % SEAT_ON_COLORS.length] : NO_SEAT.on
}
