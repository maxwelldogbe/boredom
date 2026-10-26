import { DOTS_PALETTE } from './palette'

export function playerColors(order: string[]): Record<string, string> {
  const colors: Record<string, string> = {}
  order.forEach((id, index) => {
    colors[id] = DOTS_PALETTE[index]
  })
  return colors
}
