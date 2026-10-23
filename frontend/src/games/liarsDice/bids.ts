import type { DiceBid } from '../../types/views'

/** "3 × 4s" style text for a bid. */
export function bidText(bid: Pick<DiceBid, 'quantity' | 'face'>): string {
  return `${bid.quantity} × ${bid.face}${bid.quantity === 1 ? '' : 's'}`
}

/** True if (quantity, face) beats `bid`: higher quantity, or same quantity and higher face. */
export function beats(quantity: number, face: number, bid: DiceBid | null): boolean {
  return !bid || quantity > bid.quantity || (quantity === bid.quantity && face > bid.face)
}
