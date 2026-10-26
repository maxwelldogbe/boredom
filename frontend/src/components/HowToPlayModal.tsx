import { Button } from './Button'
import { Modal } from './Modal'
import type { GameInstructions } from '../games/instructions/types'

interface HowToPlayModalProps {
  content: GameInstructions
  inGame?: boolean
  roundsToWin?: number
  pickSeconds?: number
  offlineSeconds?: number
  onClose: () => void
}

function fill(text: string, values: Record<string, number>) {
  return text.replace(/\{(\w+)\}/g, (_, key: string) => String(values[key] ?? `{${key}}`))
}

export function HowToPlayModal({
  content,
  inGame = false,
  roundsToWin = 2,
  pickSeconds = 10,
  offlineSeconds = 30,
  onClose,
}: HowToPlayModalProps) {
  const values = { roundsToWin, pickSeconds, offlineSeconds }
  return (
    <Modal
      title={content.title}
      onClose={onClose}
      closeOnBackdrop={false}
      headerActions={
        <button
          type="button"
          className="modal__close"
          aria-label="Close"
          style={{ minWidth: '44px', minHeight: '44px' }}
          onClick={onClose}
        >
          <span aria-hidden="true">×</span>
        </button>
      }
      actions={
        <Button block onClick={onClose}>
          Continue
        </Button>
      }
    >
      <div className="how-to-play">
        <p className="how-to-play__tagline">{content.tagline}</p>
        {inGame && <p className="how-to-play__note">The game keeps running</p>}
        <section>
          <h3>Goal</h3>
          <p>{fill(content.goal, values)}</p>
        </section>
        {content.visual && (() => {
          const Visual = content.visual
          return <Visual />
        })()}
        <section>
          <h3>How to play</h3>
          <ol>
            {content.steps.map((step) => (
              <li key={step}>{fill(step, values)}</li>
            ))}
          </ol>
        </section>
        <section>
          <h3>Rules</h3>
          <ul>
            {content.rules.map((rule) => (
              <li key={rule}>{fill(rule, values)}</li>
            ))}
          </ul>
        </section>
        {content.points && (
          <section>
            <h3>How points work</h3>
            <ul>
              {content.points.map((point) => (
                <li key={point}>{fill(point, values)}</li>
              ))}
            </ul>
          </section>
        )}
        {content.challenge && (
          <section>
            <h3>Not-a-real-word</h3>
            <ul>
              {content.challenge.map((item) => (
                <li key={item}>{fill(item, values)}</li>
              ))}
            </ul>
          </section>
        )}
        <section>
          <h3>Tips</h3>
          <ul>
            {content.tips.map((tip) => (
              <li key={tip}>{fill(tip, values)}</li>
            ))}
          </ul>
        </section>
        {content.reference && (
          <section>
            <h3>Quick reference</h3>
            <ul className="how-to-play__reference">
              {content.reference.map((item) => (
                <li key={`${item.left}-${item.right}`}>
                  <span>{item.left}</span> {item.verb} <span>{item.right}</span>
                </li>
              ))}
            </ul>
          </section>
        )}
      </div>
    </Modal>
  )
}
