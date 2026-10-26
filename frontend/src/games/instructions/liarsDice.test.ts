import { describe, expect, it } from 'vitest'
import { C } from '../../lib/constants'
import { liarsDiceInstructions } from './liarsDice'

function content(settings: Record<string, unknown>) {
  return liarsDiceInstructions({ settings, constants: C, playerCount: 3 })
}

describe("Liar's Dice instructions", () => {
  it('uses starting dice and turn constants without exposing dice values', () => {
    const instructions = content({ startingDice: 4, wildOnes: false, spotOn: false })
    const text = JSON.stringify(instructions)

    expect(text).toContain('Everyone starts with 4 dice.')
    expect(text).toContain(`You have ${C.DICE_TURN_MS / 1000} seconds per turn.`)
    expect(text).not.toContain('1, 2, 3')
    expect(instructions.sections).toHaveLength(0)
  })

  it('shows only the enabled optional sections', () => {
    const both = content({ startingDice: 5, wildOnes: true, spotOn: true })
    expect(both.sections?.map((section) => section.title)).toEqual(['Ones are wild', 'Spot on'])
    expect(both.sections?.[1].items).toContain('If the count is exactly the bid, you gain one die (up to 5).')

    const neither = content({ startingDice: 3, wildOnes: false, spotOn: false })
    expect(neither.sections).toHaveLength(0)
  })
})
