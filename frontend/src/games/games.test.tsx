import { act, fireEvent, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { FakeWebSocket } from '../test/fakeWebSocket'
import { guessRaceFx, hangmanFx, rpsFx, type ViewFixture } from '../test/fixtures'
import { renderWithRoom } from '../test/render'
import { GuessRaceGame } from './guessRace/GuessRaceGame'
import { HangmanGame } from './hangman/HangmanGame'
import { RpsGame } from './rps/RpsGame'

beforeEach(() => FakeWebSocket.reset())

function props<F extends ViewFixture>(fx: F) {
  const send = vi.fn(async () => true)
  return { view: fx.push.view as F['push']['view'], me: fx.me, room: fx.room, send }
}

describe('RpsGame (real backend views)', () => {
  it('picking: three choices, opponent has picked', () => {
    const p = props(rpsFx.duelPickingOpponentPicked)
    renderWithRoom(<RpsGame {...p} />)
    expect(screen.getAllByRole('button', { name: /Rock|Paper|Scissors/ })).toHaveLength(3)
    expect(screen.getByText(/has picked!/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Paper/ }))
    expect(p.send).toHaveBeenCalledWith({ type: 'pick', choice: 'paper' })
  })

  it('after picking: locked in, buttons disabled, waiting', () => {
    renderWithRoom(<RpsGame {...props(rpsFx.duelPickedWaiting)} />)
    expect(screen.getByText('Locked in!')).toBeInTheDocument()
    screen.getAllByRole('button', { name: /Rock|Paper|Scissors/ }).forEach((b) => expect(b).toBeDisabled())
  })

  it('reveal shows both picks and the round result', () => {
    const fx = rpsFx.duelReveal
    renderWithRoom(<RpsGame {...props(fx)} />)
    expect(screen.getByText(/^You: /)).toBeInTheDocument()
    expect(screen.getByText(/wins the round|You win the round|Tie|wins the match|You win the match/)).toBeInTheDocument()
  })

  it('done shows the champion', () => {
    renderWithRoom(<RpsGame {...props(rpsFx.duelDone)} />)
    expect(screen.getByText(/the champion!/)).toBeInTheDocument()
  })

  it('bracket: bye, eliminated and bracket list', () => {
    const { unmount } = renderWithRoom(<RpsGame {...props(rpsFx.bracketBye)} />)
    expect(screen.getByText(/You have a bye/)).toBeInTheDocument()
    expect(screen.getByText('bye')).toBeInTheDocument()
    unmount()
    renderWithRoom(<RpsGame {...props(rpsFx.bracketEliminated)} />)
    expect(screen.getByText(/You're out/)).toBeInTheDocument()
  })
})

describe('GuessRaceGame (real backend views)', () => {
  it('scramble: tiles, input and a guess action', async () => {
    const fx = guessRaceFx.scrambleGuessing
    const p = props(fx)
    renderWithRoom(<GuessRaceGame {...p} />)
    expect(screen.getByText('🔤 Word Scramble')).toBeInTheDocument()
    expect(screen.getByLabelText(/Scrambled letters/)).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Your guess'), { target: { value: '  apple ' } })
    await act(async () => fireEvent.click(screen.getByRole('button', { name: 'Guess' })))
    expect(p.send).toHaveBeenCalledWith({ type: 'guess', text: 'apple' })
    expect(screen.getByLabelText('Your guess')).toHaveValue('')
  })

  it('emoji: shows my wrong guess feedback', () => {
    const fx = guessRaceFx.emojiWrongGuess
    renderWithRoom(<GuessRaceGame {...props(fx)} />)
    expect(screen.getByText('😀 Emoji Guess')).toBeInTheDocument()
    expect(screen.getByText(/isn't it/)).toBeInTheDocument()
  })

  it('round over: the answer is shown, input is gone', () => {
    const fx = guessRaceFx.scrambleRoundOver
    renderWithRoom(<GuessRaceGame {...props(fx)} />)
    expect(screen.getByText('The answer was')).toBeInTheDocument()
    expect(screen.getByText(fx.push.view.answer!)).toBeInTheDocument()
    expect(screen.queryByLabelText('Your guess')).not.toBeInTheDocument()
  })
})

describe('HangmanGame (real backend views)', () => {
  it('setter picks a word (letters only, uppercased) with an optional hint', async () => {
    const p = props(hangmanFx.settingSetter)
    renderWithRoom(<HangmanGame {...p} />)
    fireEvent.change(screen.getByLabelText('Secret word'), { target: { value: 'ze-bra1' } })
    expect(screen.getByLabelText('Secret word')).toHaveValue('ZEBRA')
    fireEvent.change(screen.getByLabelText('Hint (optional)'), { target: { value: 'Stripes' } })
    await act(async () => fireEvent.click(screen.getByRole('button', { name: 'Use this word' })))
    expect(p.send).toHaveBeenCalledWith({ type: 'setWord', word: 'ZEBRA', hint: 'Stripes' })
  })

  it('guesser waits while the setter chooses', () => {
    renderWithRoom(<HangmanGame {...props(hangmanFx.settingGuesser)} />)
    expect(screen.getByText(/Waiting for .* to choose a word/)).toBeInTheDocument()
  })

  it('guesser sees blanks, marked keys and can guess a letter', () => {
    const fx = hangmanFx.guessingGuesser
    const p = props(fx)
    renderWithRoom(<HangmanGame {...p} />)
    const keyboard = screen.getByLabelText('Letters')
    for (const letter of fx.push.view.wrong) expect(within(keyboard).getByRole('button', { name: `${letter}, wrong` })).toBeDisabled()
    const right = fx.push.view.guessed.find((l) => !fx.push.view.wrong.includes(l))!
    expect(within(keyboard).getByRole('button', { name: `${right}, correct` })).toBeDisabled()
    fireEvent.click(within(keyboard).getByRole('button', { name: 'Q' }))
    expect(p.send).toHaveBeenCalledWith({ type: 'guessLetter', letter: 'Q' })
    expect(screen.getByRole('img', { name: `${fx.push.view.wrongCount} of 6 wrong guesses` })).toBeInTheDocument()
  })

  it('setter sees the word but no keyboard', () => {
    const fx = hangmanFx.guessingSetter
    renderWithRoom(<HangmanGame {...props(fx)} />)
    expect(screen.queryByLabelText('Letters')).not.toBeInTheDocument()
    expect(screen.getByText(/You can't guess your own word/)).toBeInTheDocument()
  })

  it('round over and setter win messages', () => {
    const { unmount } = renderWithRoom(<HangmanGame {...props(hangmanFx.roundOverGuessers)} />)
    expect(screen.getByText(/Solved! The word was/)).toBeInTheDocument()
    unmount()
    renderWithRoom(<HangmanGame {...props(hangmanFx.roundOverSetterWins)} />)
    expect(screen.getByText(/this round! The word was/)).toBeInTheDocument()
  })
})
