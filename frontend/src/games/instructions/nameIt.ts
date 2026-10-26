import type { GameInstructions, InstructionContext } from './types'

export function nameItInstructions(context: InstructionContext): GameInstructions {
  const turnSeconds = Number(context.settings.turnSeconds)
  const challenges = context.settings.challenges === true
  const allowCustomTopics = context.settings.allowCustomTopics === true
  const challengeSeconds = context.constants.NAMEIT_CHALLENGE_WINDOW_MS / 1000
  const voteSeconds = context.constants.NAMEIT_VOTE_MS / 1000
  const topicSeconds = context.constants.NAMEIT_TOPIC_MS / 1000
  const topicSuggestions = context.constants.NAMEIT_TOPIC_SUGGESTIONS

  return {
    title: '🔥 Name It Survival',
    tagline: "Name something in the topic. Hesitate, repeat, or get it wrong and you're out.",
    goal: 'Be the last player standing.',
    steps: [
      'The game starts with a topic, like countries, fruits, or football clubs.',
      'Players take turns naming one thing that fits the topic. For example, for fruits you might say "mango".',
      `You have ${turnSeconds} seconds to answer on your turn. Type your answer and send it.`,
      "You can't repeat an answer that has already been said by anyone.",
      "If you run out of time, repeat an answer, or give an answer that doesn't fit, you're out of the game.",
      'When a player is out, the round ends. A new round starts with a new topic and everyone who is still in keeps playing.',
      'Keep going until only one player is left. That player wins.',
    ],
    sections: [
      {
        title: 'Who picks the topic?',
        items: [
          'The first player in seat order picks the first topic. After that, the player who just got knocked out picks the next one.',
          allowCustomTopics
            ? `They can choose from ${topicSuggestions} random topics or type their own.`
            : `They choose from ${topicSuggestions} random topics.`,
          `They have ${topicSeconds} seconds. If they run out of time, a random topic is chosen.`,
        ],
      },
      ...(challenges
        ? [
            {
              title: 'Think an answer is wrong?',
              items: [
                `After someone answers, any other player can tap Challenge within ${challengeSeconds} seconds.`,
                `The game pauses and the other players vote Valid or Invalid for ${voteSeconds} seconds.`,
                'If most players vote Invalid, the player who gave the answer is out. If the vote is tied, or nobody votes, the answer stays valid.',
                "Challenge carefully. Only challenge answers you're sure don't fit the topic.",
              ],
            },
          ]
        : []),
    ],
    rules: [
      "Capital letters, spaces, and punctuation don't matter when checking for repeats.",
      'Answers can be up to 40 characters.',
      'Only the player whose turn it is can answer.',
      'Players who are out can keep watching.',
      'The last player standing wins. Players are ranked by how long they lasted.',
    ],
    tips: [
      'Have a few answers ready before your turn. Time goes fast.',
      "Save the obvious answers for later and don't repeat what's been said.",
      'Think of less common answers early, so the easy ones are used up before they get to you.',
    ],
  }
}
