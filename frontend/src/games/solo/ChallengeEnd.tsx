import { Button } from '../../components/Button'
import { friendlyError } from '../../lib/errors'
import { useRoomActions, useRoomState } from '../../state/context'
import type { ChallengePush } from '../../types/views'
import './solo.css'

function detailLine(push: ChallengePush): string {
  const result = push.view.soloResult
  if (!result) return ''
  switch (push.gameId) {
    case 'solo_guess_run':
      return `Solved ${push.view.solved}, skipped ${push.view.skipped}`
    case 'solo_name_it':
      return push.view.completed
        ? `You named every one of the ${push.view.topic.name.toLowerCase()}!`
        : `Named ${result.score} ${push.view.topic.name.toLowerCase()}`
    case 'solo_hangman': {
      const last = typeof result.detail.lastWord === 'string' ? result.detail.lastWord.toUpperCase() : null
      const words = `Solved ${result.score} ${result.score === 1 ? 'word' : 'words'}`
      return last ? `${words}. The last word was ${last}.` : words
    }
  }
}

/** The end of a solo run: score, personal best, and what next. */
export function ChallengeEnd({ busy, onQuit }: { busy: boolean; onQuit: (to: string) => Promise<void> }) {
  const push = useRoomState().game as unknown as ChallengePush | null
  const { soloAgain, toast } = useRoomActions()
  const result = push?.view.soloResult ?? null
  if (!push || !result) return null
  const again = async () => {
    try {
      await soloAgain()
    } catch (err) {
      toast(friendlyError(err), 'error')
    }
  }
  return (
    <section className="card stack solo-end" aria-labelledby="solo-end-score">
      {result.isNewBest && (
        <p className="solo-run__best-banner" role="status">
          New personal best!
        </p>
      )}
      <h2 id="solo-end-score" className="solo-run__score" aria-live="polite">
        <span className="visually-hidden">Your score: </span>
        {result.score}
      </h2>
      {result.best !== null && <p className="muted">Best: {result.best}</p>}
      <p>{detailLine(push)}</p>
      <Button block onClick={() => void again()} disabled={busy}>
        Play again
      </Button>
      <Button variant="secondary" block onClick={() => void onQuit('/solo')} disabled={busy}>
        Change game
      </Button>
      <Button variant="ghost" block onClick={() => void onQuit('/solo')} disabled={busy}>
        Back
      </Button>
    </section>
  )
}
