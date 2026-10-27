import { copyText } from '../lib/clipboard'
import { useRoomActions } from '../state/context'
import { Button } from './Button'

interface CopyButtonProps {
  text: string
  label: string
  copiedMessage: string
  variant?: 'primary' | 'secondary'
  /** Full width (default), or a compact inline button. */
  block?: boolean
  /** Accessible name when the visible label is short ("Copy"). */
  ariaLabel?: string
}

/** Copies `text` and confirms with a toast. */
export function CopyButton({ text, label, copiedMessage, variant = 'secondary', block = true, ariaLabel }: CopyButtonProps) {
  const { toast } = useRoomActions()
  return (
    <Button
      variant={variant}
      block={block}
      aria-label={ariaLabel}
      onClick={async () => {
        const ok = await copyText(text)
        toast(ok ? copiedMessage : "Couldn't copy. Select and copy it by hand.", ok ? 'info' : 'error')
      }}
    >
      {label}
    </Button>
  )
}
