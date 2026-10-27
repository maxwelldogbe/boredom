/** Remove, block and report dialogs for a player named by tag (friends page, recent players). */
import { blockPlayer, removeFriend, reportPlayer } from '../lib/social'
import { useRoomActions } from '../state/context'
import { useSocial } from '../state/socialContext'
import type { PlayerCard } from '../types/protocol'
import { ConfirmDialog, ReportDialog } from './SocialDialogs'

export type PlayerDialogKind = 'remove' | 'block' | 'report'

export function PlayerDialogs({
  dialog,
  onClose,
  onBlocked,
}: {
  dialog: { kind: string; friend: PlayerCard } | null
  onClose: () => void
  onBlocked?: (tag: string) => void
}) {
  const social = useSocial()
  const { toast } = useRoomActions()
  if (!dialog) return null
  const { friend } = dialog
  if (dialog.kind === 'remove')
    return (
      <ConfirmDialog
        title={`Remove ${friend.nickname}?`}
        confirmLabel="Remove friend"
        onClose={onClose}
        onConfirm={async () => {
          await removeFriend(friend.tag)
          social.update((d) => ({ ...d, friends: d.friends.filter((f) => f.tag !== friend.tag) }))
          toast(`${friend.nickname} was removed from your friends.`)
        }}
      >
        <p>They won't be told. You can add each other again later.</p>
      </ConfirmDialog>
    )
  if (dialog.kind === 'block')
    return (
      <ConfirmDialog
        title={`Block ${friend.nickname}?`}
        confirmLabel="Block"
        onClose={onClose}
        onConfirm={async () => {
          await blockPlayer(friend.tag)
          social.update((d) => ({
            ...d,
            friends: d.friends.filter((f) => f.tag !== friend.tag),
            incoming: d.incoming.filter((r) => r.tag !== friend.tag),
            outgoing: d.outgoing.filter((r) => r.tag !== friend.tag),
            blocked: d.blocked.some((b) => b.tag === friend.tag) ? d.blocked : [friend, ...d.blocked],
          }))
          onBlocked?.(friend.tag)
          toast(`${friend.nickname} is blocked.`)
        }}
      >
        <p>
          You won't see each other in friends or recent players, and neither of you can send requests or invites. They
          won't be told. You can still end up in the same room.
        </p>
      </ConfirmDialog>
    )
  if (dialog.kind !== 'report') return null
  return (
    <ReportDialog
      nickname={friend.nickname}
      onClose={onClose}
      onSubmit={async (reason, note) => {
        await reportPlayer(friend.tag, reason, note)
        toast('Thanks. Our team will take a look.')
      }}
    />
  )
}

