import QRCode from 'qrcode'
import { useEffect, useState } from 'react'

/** QR image for a URL, generated in the browser. */
export function QrCode({ url }: { url: string }) {
  const [src, setSrc] = useState<string | null>(null)
  const [failed, setFailed] = useState(false)
  useEffect(() => {
    let active = true
    QRCode.toDataURL(url, { margin: 1, width: 240 })
      .then((data) => active && setSrc(data))
      .catch(() => active && setFailed(true))
    return () => {
      active = false
    }
  }, [url])
  if (failed) return <p className="muted">Couldn't make a QR code. Share the link instead.</p>
  if (!src) return <p className="muted">Making QR code…</p>
  return <img className="qr" src={src} width={240} height={240} alt={`QR code for ${url}`} />
}
