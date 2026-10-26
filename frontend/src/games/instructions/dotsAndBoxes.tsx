import type { InstructionContext, GameInstructions } from './types'
import { DotsDiagram } from './DotsDiagram'

export function dotsAndBoxesInstructions(context: InstructionContext): GameInstructions {
  const size = Number(context.settings.size) || 5
  const turnSeconds = context.constants.DOTS_TURN_MS / 1000
  return {
    title: '🔲 Dots and Boxes',
    tagline: "Draw lines, claim boxes, and don't help your rivals.",
    goal: 'Claim more boxes than anyone else.',
    visual: DotsDiagram,
    steps: [
      'The board is a grid of dots. On your turn, draw one line between two neighboring dots by tapping the space between them.',
      'Every player draws in their own bright color, so you can always see who drew which line. Find your color in the player list above the board.',
      'When your line completes the fourth side of a box, you claim it. The box fills with your color and you get 1 point.',
      'Claim a box and you play again. Keep going until you draw a line that doesn\'t complete a box.',
      'The game ends when every box is claimed. The player with the most boxes wins.',
    ],
    rules: [
      `The board has ${size} x ${size} boxes. Dots and Boxes is for 2 to 4 players.`,
      "You can only draw on your turn. Look for the turn banner and the highlighted name.",
      "You can't draw a line that is already drawn.",
      `You have ${turnSeconds} seconds per turn. If time runs out, a line is drawn for you.`,
      'If you go offline for a while, the game draws for you so everyone else can keep playing.',
      'If players tie for the most boxes, they share the win.',
    ],
    tips: [
      'Try not to draw the third side of a box. That lets the next player claim it.',
      'Near the end, count the boxes. Sometimes you must give some boxes away so you can win the rest.',
      'If you can claim a box, check whether it sets up another one. A run of boxes in one turn wins games.',
    ],
  }
}
