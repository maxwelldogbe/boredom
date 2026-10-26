import { describe, expect, it } from 'vitest'
import { C } from '../../lib/constants'
import { gameInstructions } from './index'
import { nameItInstructions } from './nameIt'

const defaults = { turnSeconds: 10, challenges: true, allowCustomTopics: false }

describe('Name It Survival instructions', () => {
  it('changes challenge and topic text with settings', () => {
    const enabled = nameItInstructions({ settings: defaults, constants: C, playerCount: 3 })
    expect(enabled.sections?.map((section) => section.title)).toEqual(['Who picks the topic?', 'Think an answer is wrong?'])
    expect(JSON.stringify(enabled)).toContain(`within ${C.NAMEIT_CHALLENGE_WINDOW_MS / 1000} seconds`)
    expect(JSON.stringify(enabled)).toContain(`for ${C.NAMEIT_VOTE_MS / 1000} seconds`)
    expect(JSON.stringify(enabled)).toContain(`${C.NAMEIT_TOPIC_SUGGESTIONS} random topics.`)
    expect(JSON.stringify(enabled)).toContain(`They have ${C.NAMEIT_TOPIC_MS / 1000} seconds.`)

    const disabled = nameItInstructions({
      settings: { turnSeconds: 20, challenges: false, allowCustomTopics: true },
      constants: C,
      playerCount: 3,
    })
    expect(disabled.sections?.map((section) => section.title)).toEqual(['Who picks the topic?'])
    expect(JSON.stringify(disabled)).toContain('or type their own.')
    expect(JSON.stringify(disabled)).not.toContain('Think an answer is wrong?')
    expect(JSON.stringify(disabled)).toContain('You have 20 seconds to answer')
  })

  it('has instructions for every backend game id with non-empty content', () => {
    const defaultsByGame = {
      rps: { bestOf: 3, mode: 'duel' },
      guess_race: { content: 'mixed', rounds: 10, difficulty: 'mixed' },
      hangman: { mode: 'group' },
      dots_and_boxes: { size: 5 },
      liars_dice: { startingDice: 5, wildOnes: false, spotOn: false },
      name_it: defaults,
    } as const

    for (const [id, settings] of Object.entries(defaultsByGame)) {
      const instructions = gameInstructions(id as keyof typeof defaultsByGame, {
        settings,
        constants: C,
        playerCount: 3,
      })
      expect(instructions, id).not.toBeNull()
      expect(instructions?.title, id).toBeTruthy()
      expect(instructions?.tagline, id).toBeTruthy()
      expect(instructions?.goal, id).toBeTruthy()
      expect(instructions?.steps.length, id).toBeGreaterThan(0)
      expect(instructions?.rules.length, id).toBeGreaterThan(0)
      expect(instructions?.tips.length, id).toBeGreaterThan(0)
    }
  })
})
