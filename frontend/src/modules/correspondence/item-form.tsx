import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { api, unwrap } from '@/api/client'
import { handleServerError } from '@/lib/handle-server-error'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import {
  STATUSES,
  TYPES,
  corKeys,
  label,
  useContactOptions,
  type Item,
} from './api'
import { Choice } from './choice'

const today = () => new Date().toISOString().slice(0, 10)

/** Register a new item, or a reply to `replyTo` (an outgoing item addressed to its sender by default). */
export function ItemDialog({
  projectId,
  replyTo,
  open,
  onClose,
  onCreated,
}: {
  projectId: number
  replyTo?: Item | null
  open: boolean
  onClose: () => void
  onCreated: (item: Item) => void
}) {
  const queryClient = useQueryClient()
  const { data: contacts = [] } = useContactOptions()
  const replyDirection =
    replyTo?.direction === 'outgoing' ? 'incoming' : 'outgoing'
  const [type, setType] = useState<string>(replyTo ? replyTo.type : 'letter')
  const [direction, setDirection] = useState<string>(
    replyTo ? replyDirection : 'outgoing'
  )
  const [status, setStatus] = useState<string>(
    replyTo ? (replyDirection === 'outgoing' ? 'sent' : 'received') : 'draft'
  )
  const [sender, setSender] = useState(
    replyTo && replyDirection === 'incoming' && replyTo.recipient_contact_ids[0]
      ? String(replyTo.recipient_contact_ids[0])
      : ''
  )
  const [recipients, setRecipients] = useState<number[]>(
    replyTo?.sender_contact_id && replyDirection === 'outgoing'
      ? [replyTo.sender_contact_id]
      : []
  )

  const create = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      unwrap(api.POST('/api/v1/correspondence/', { body: body as never })),
    onSuccess: (item) => {
      toast.success(`${item.reference} registered`)
      void queryClient.invalidateQueries({ queryKey: corKeys.all(projectId) })
      if (replyTo) {
        void queryClient.invalidateQueries({
          queryKey: corKeys.one(replyTo.id),
        })
        void queryClient.invalidateQueries({ queryKey: ['correspondence'] })
      }
      onCreated(item)
    },
    onError: handleServerError,
  })

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className='sm:max-w-2xl'>
        <DialogHeader>
          <DialogTitle>
            {replyTo
              ? `Reply to ${replyTo.reference}`
              : 'Register correspondence'}
          </DialogTitle>
          {replyTo ? (
            <DialogDescription>{replyTo.subject}</DialogDescription>
          ) : null}
        </DialogHeader>
        <form
          id='cor-form'
          className='grid max-h-[70vh] grid-cols-2 gap-3 overflow-y-auto pe-1'
          onSubmit={(e) => {
            e.preventDefault()
            const data = new FormData(e.currentTarget)
            const text = (k: string) =>
              String(data.get(k) ?? '').trim() || undefined
            create.mutate({
              project_id: projectId,
              subject: text('subject'),
              body: text('body'),
              type,
              custom_type: type === 'other' ? text('custom_type') : undefined,
              direction,
              status,
              external_reference: text('external_reference'),
              sender_contact_id: sender ? Number(sender) : undefined,
              recipient_contact_ids: recipients,
              date_sent: text('date_sent'),
              date_received: text('date_received'),
              response_required_by: text('response_required_by'),
              in_reply_to_id: replyTo?.id,
            })
          }}
        >
          <div className='col-span-2 grid gap-1.5'>
            <Label htmlFor='cor-subject'>Subject</Label>
            <Input
              id='cor-subject'
              name='subject'
              required
              maxLength={300}
              defaultValue={
                replyTo
                  ? replyTo.subject.startsWith('Re:')
                    ? replyTo.subject
                    : `Re: ${replyTo.subject}`.slice(0, 300)
                  : ''
              }
            />
          </div>
          <div className='grid gap-1.5'>
            <Label>Type</Label>
            <Choice
              value={type}
              onChange={setType}
              options={TYPES.map((t) => ({
                value: t,
                label: t === 'other' ? 'Other (custom)' : label(t),
              }))}
            />
          </div>
          <div className='grid gap-1.5'>
            <Label>Direction</Label>
            <Choice
              value={direction}
              onChange={setDirection}
              options={[
                { value: 'outgoing', label: 'Outgoing' },
                { value: 'incoming', label: 'Incoming' },
              ]}
            />
          </div>
          {type === 'other' ? (
            <div className='grid gap-1.5'>
              <Label htmlFor='cor-custom'>Custom type</Label>
              <Input
                id='cor-custom'
                name='custom_type'
                maxLength={60}
                required
              />
            </div>
          ) : null}
          <div className='grid gap-1.5'>
            <Label>Status</Label>
            <Choice
              value={status}
              onChange={setStatus}
              options={STATUSES.filter((s) => s !== 'responded').map((s) => ({
                value: s,
                label: label(s),
              }))}
            />
          </div>
          <div className='grid gap-1.5'>
            <Label>From (contact)</Label>
            <Choice
              value={sender}
              onChange={setSender}
              emptyLabel={direction === 'outgoing' ? 'Us' : 'Unknown'}
              options={contacts.map((c) => ({
                value: String(c.id),
                label: c.name,
              }))}
            />
          </div>
          <div className='grid gap-1.5'>
            <Label htmlFor='cor-ext'>Their reference</Label>
            <Input id='cor-ext' name='external_reference' maxLength={100} />
          </div>
          <div className='grid gap-1.5'>
            <Label htmlFor='cor-sent'>Date sent</Label>
            <Input
              id='cor-sent'
              name='date_sent'
              type='date'
              defaultValue={direction === 'outgoing' ? today() : ''}
            />
          </div>
          <div className='grid gap-1.5'>
            <Label htmlFor='cor-received'>Date received</Label>
            <Input
              id='cor-received'
              name='date_received'
              type='date'
              defaultValue={direction === 'incoming' ? today() : ''}
            />
          </div>
          <div className='grid gap-1.5'>
            <Label htmlFor='cor-due'>Response required by</Label>
            <Input id='cor-due' name='response_required_by' type='date' />
          </div>
          <div className='col-span-2 grid gap-1.5'>
            <Label>To</Label>
            <div className='grid max-h-36 grid-cols-2 gap-1 overflow-y-auto rounded-md border p-2 text-sm'>
              {contacts.length === 0 ? (
                <span className='text-muted-foreground'>No contacts.</span>
              ) : null}
              {contacts.map((c) => (
                <label key={c.id} className='flex items-center gap-1.5'>
                  <Checkbox
                    checked={recipients.includes(c.id)}
                    onCheckedChange={(on) =>
                      setRecipients((r) =>
                        on === true
                          ? [...r, c.id]
                          : r.filter((id) => id !== c.id)
                      )
                    }
                  />
                  <span className='truncate'>{c.name}</span>
                </label>
              ))}
            </div>
          </div>
          <div className='col-span-2 grid gap-1.5'>
            <Label htmlFor='cor-body'>Body or summary</Label>
            <Textarea id='cor-body' name='body' rows={6} />
          </div>
        </form>
        <DialogFooter>
          <Button variant='outline' onClick={onClose}>
            Cancel
          </Button>
          <Button type='submit' form='cor-form' disabled={create.isPending}>
            {replyTo ? 'Register reply' : 'Register'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
