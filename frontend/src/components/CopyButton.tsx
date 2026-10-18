import { copyText } from '../lib/clipboard'
import { useRoomActions } from '../state/context'
import { Button } from './Button'

interface CopyButtonProps {
  text: string
  label: string
  copiedMessage: string
  variant?: 'primary' | 'secondary'
}

/** Copies `text` and confirms with a toast. */
export function CopyButton({ text, label, copiedMessage, variant = 'secondary' }: CopyButtonProps) {
  const { toast } = useRoomActions()
  return (
    <Button
      variant={variant}
      block
      onClick={async () => {
        const ok = await copyText(text)
        toast(ok ? copiedMessage : "Couldn't copy. Select and copy it by hand.", ok ? 'info' : 'error')
      }}
    >
      {label}
    </Button>
  )
}
