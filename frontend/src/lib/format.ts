/** Points as the server sends them (up to 2 decimals): 50 -> "50", 66.666 -> "66.67". */
export function formatPoints(n: number): string {
  return String(Math.round(n * 100) / 100)
}
