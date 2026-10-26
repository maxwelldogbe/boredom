import type { GameInstructions, InstructionContext } from './types'

export function liarsDiceInstructions(context: InstructionContext): GameInstructions {
  const startingDice = Number(context.settings.startingDice)
  const turnSeconds = context.constants.DICE_TURN_MS / 1000
  const sections = []

  if (context.settings.wildOnes === true) {
    sections.push({
      title: 'Ones are wild',
      items: [
        'Dice showing 1 count as any number, so they help every bid.',
        'The exception: when the bid is about 1s, only 1s are counted.',
      ],
    })
  }
  if (context.settings.spotOn === true) {
    sections.push({
      title: 'Spot on',
      items: [
        'Instead of raising or calling Liar, you can call "Spot on!" when you think the last bid is exactly right.',
        `If the count is exactly the bid, you gain one die (up to ${startingDice}).`,
        'If the count is higher or lower, you lose one die.',
      ],
    })
  }

  return {
    title: "🎲 Liar's Dice",
    tagline: 'Bluff, bet, and catch the liars.',
    goal: 'Be the last player with dice.',
    steps: [
      `Everyone starts with ${startingDice} dice. You roll them in secret and only you can see your own dice.`,
      'On your turn, make a bid: a guess about ALL the dice on the table, including other players\' hidden dice. For example, "four 3s" means you claim there are at least four dice showing 3 in total.',
      'Each new bid must be higher than the last one: either more dice, or the same number of dice with a higher face.',
      'Don\'t believe the last bid? Call "Liar!" instead of bidding.',
      'When someone calls Liar, everyone reveals their dice and the dice are counted.',
      'If the bid was true (there are at least that many), the player who called Liar loses one die. If it was false, the player who made the bid loses one die.',
      'A new round starts with fresh rolls. When a player has no dice left, they are out. The last player with dice wins.',
    ],
    sections,
    rules: [
      'The first player of a round must make a bid. You can\'t call Liar before anyone has bid.',
      'The first round starts with a random player. After that, whoever lost the last challenge starts the next round. If that player was knocked out, the next player starts.',
      `You have ${turnSeconds} seconds per turn. If time runs out, the smallest possible higher bid is made for you. If no higher bid is possible, Liar is called for you.`,
      'Your own dice stay hidden from everyone else until a challenge reveals them.',
      'Players who are out can keep watching.',
    ],
    tips: [
      'Look at your own dice first. If you hold several 4s, a bid on 4s is safer for you.',
      'The more dice on the table, the more likely a high bid is true. As dice disappear, big bids get riskier.',
      'Pay attention to what other players bid. A sudden jump may be a bluff.',
      'Mix honest bids with bluffs so nobody can read you.',
    ],
  }
}
