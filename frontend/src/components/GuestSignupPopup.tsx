import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { FLYER, SHOW_DELAY_MS } from '../config/guestPopup'
import { convertPopup, dismissPopup, markPopupShown, popupDue } from '../lib/guestPopup'
import { getProfile } from '../lib/profileStore'
import type { GameResult } from '../types/protocol'
import { Button } from './Button'
import { Modal } from './Modal'

const TITLE = 'Make your profile permanent'
const OFFER = 'Save your avatar, stats, and friends on any device.'
const WAIT_FOR_DIALOG_MS = 300

// Results already considered, so a remount (or StrictMode) never shows it twice for one game.
const considered = new WeakSet<GameResult[]>()

/** The guest signup popup on the final results screen: about 1.5 s after the results show,
 *  once no other dialog is open, when the counters say it is due. */
export function GuestSignupPopup({ roomCode, results }: { roomCode: string; results: GameResult[] | null }) {
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const [imageFailed, setImageFailed] = useState(false)
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    if (!results || considered.has(results)) return
    if (getProfile()?.type !== 'guest' || !popupDue()) return
    const tryShow = () => {
      // Never over another dialog (leave, forfeit, how to play): wait for it to close.
      if (document.querySelector('.modal')) {
        timer.current = setTimeout(tryShow, WAIT_FOR_DIALOG_MS)
        return
      }
      if (considered.has(results)) return
      considered.add(results)
      markPopupShown()
      setOpen(true)
    }
    timer.current = setTimeout(tryShow, SHOW_DELAY_MS)
    return () => {
      if (timer.current) clearTimeout(timer.current)
    }
  }, [results])

  if (!open) return null

  const later = () => {
    dismissPopup()
    setOpen(false)
  }
  const signUp = () => {
    convertPopup()
    setOpen(false)
    navigate(`/signup?next=${encodeURIComponent(`/room/${roomCode}`)}`)
  }
  const withImage = FLYER.src !== null && !imageFailed

  return (
    <Modal
      title={TITLE}
      hideTitle={withImage}
      className="guest-popup"
      closeOnBackdrop={false}
      onClose={later}
      headerActions={
        <button type="button" className="modal__close" aria-label="Close" onClick={later}>
          ✕
        </button>
      }
      actions={
        <>
          <Button block onClick={signUp}>
            Create free account
          </Button>
          <Button variant="ghost" block onClick={later}>
            Maybe later
          </Button>
        </>
      }
    >
      {withImage && (
        <img className="guest-popup__flyer" src={FLYER.src!} alt={FLYER.alt} onError={() => setImageFailed(true)} />
      )}
      <p className="guest-popup__offer">{OFFER}</p>
    </Modal>
  )
}
