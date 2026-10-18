import { Button } from '../../components/Button'
import { CopyButton } from '../../components/CopyButton'
import { QrCode } from './QrCode'

/** Copy link, Web Share (where available), WhatsApp and a collapsible QR code (plan 6.1). */
export function InvitePanel({ code }: { code: string }) {
  const url = `${window.location.origin}/join/${code}`
  const text = `Join my game on Boredom! Room ${code}`
  const canShare = typeof navigator.share === 'function' && window.isSecureContext
  return (
    <section className="card stack" aria-labelledby="invite-title">
      <h2 id="invite-title" className="section-title">
        Invite friends
      </h2>
      <p className="invite__url">{url}</p>
      <CopyButton text={url} label="Copy link" copiedMessage="Link copied" />
      {canShare && (
        <Button
          variant="secondary"
          block
          onClick={() => navigator.share({ title: 'Boredom', text, url }).catch(() => undefined)}
        >
          Share…
        </Button>
      )}
      <a
        className="btn btn--secondary btn--block"
        href={`https://wa.me/?text=${encodeURIComponent(`${text} ${url}`)}`}
        target="_blank"
        rel="noreferrer"
      >
        Send on WhatsApp
      </a>
      <details className="invite__qr">
        <summary>Show QR code</summary>
        <QrCode url={url} />
      </details>
    </section>
  )
}
