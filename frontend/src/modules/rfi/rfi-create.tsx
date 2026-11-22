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
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import {
  PARTIES,
  PRIORITIES,
  label,
  rfiKeys,
  useContactOptions,
  useRfiUsers,
  type Rfi,
} from './api'
import { Choice } from './choice'

type Impact = 'cost_impact' | 'schedule_impact' | 'scope_impact'

/** Raise an RFI, as a draft or issued straight away. */
export function RfiCreateDialog({
  projectId,
  open,
  onClose,
  onCreated,
}: {
  projectId: number
  open: boolean
  onClose: () => void
  onCreated: (rfi: Rfi) => void
}) {
  const queryClient = useQueryClient()
  const { data: users = [] } = useRfiUsers()
  const { data: contacts = [] } = useContactOptions()
  const [priority, setPriority] = useState('medium')
  const [party, setParty] = useState('designer')
  const [userId, setUserId] = useState('')
  const [contactId, setContactId] = useState('')
  const [impacts, setImpacts] = useState<Record<Impact, boolean>>({
    cost_impact: false,
    schedule_impact: false,
    scope_impact: false,
  })

  const create = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      unwrap(api.POST('/api/v1/rfis/', { body: body as never })),
    onSuccess: (rfi) => {
      toast.success(`${rfi.code} raised`)
      void queryClient.invalidateQueries({ queryKey: rfiKeys.all(projectId) })
      onCreated(rfi)
    },
    onError: handleServerError,
  })

  const submit = (form: HTMLFormElement, issue: boolean) => {
    const data = new FormData(form)
    const text = (k: string) => String(data.get(k) ?? '').trim() || undefined
    create.mutate({
      project_id: projectId,
      subject: text('subject'),
      question: text('question'),
      discipline: text('discipline'),
      location: text('location'),
      due_date: text('due_date'),
      priority,
      status: issue ? 'open' : 'draft',
      ball_in_court: issue ? party : undefined,
      addressed_to_user_id: userId ? Number(userId) : undefined,
      addressed_to_contact_id: contactId ? Number(contactId) : undefined,
      ...impacts,
      cost_impact_amount: impacts.cost_impact ? text('cost_amount') : undefined,
      schedule_impact_days: impacts.schedule_impact
        ? Number(text('days') ?? 0) || undefined
        : undefined,
    })
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className='sm:max-w-2xl'>
        <DialogHeader>
          <DialogTitle>Raise an RFI</DialogTitle>
        </DialogHeader>
        <form
          id='rfi-create'
          className='grid grid-cols-2 gap-3'
          onSubmit={(e) => {
            e.preventDefault()
            const issue =
              (e.nativeEvent as SubmitEvent).submitter?.getAttribute(
                'value'
              ) === 'issue'
            submit(e.currentTarget, issue)
          }}
        >
          <div className='col-span-2 grid gap-1.5'>
            <Label htmlFor='rfi-subject'>Subject</Label>
            <Input id='rfi-subject' name='subject' required maxLength={300} />
          </div>
          <div className='col-span-2 grid gap-1.5'>
            <Label htmlFor='rfi-question'>Question</Label>
            <Textarea id='rfi-question' name='question' rows={5} required />
          </div>
          <div className='grid gap-1.5'>
            <Label htmlFor='rfi-discipline'>Discipline</Label>
            <Input
              id='rfi-discipline'
              name='discipline'
              placeholder='e.g. Mechanical'
              maxLength={60}
            />
          </div>
          <div className='grid gap-1.5'>
            <Label htmlFor='rfi-location'>Location</Label>
            <Input id='rfi-location' name='location' maxLength={200} />
          </div>
          <div className='grid gap-1.5'>
            <Label>Addressed to (user)</Label>
            <Choice
              value={userId}
              onChange={setUserId}
              emptyLabel='Nobody'
              options={users.map((u) => ({
                value: String(u.id),
                label: u.name,
              }))}
            />
          </div>
          <div className='grid gap-1.5'>
            <Label>Addressed to (contact)</Label>
            <Choice
              value={contactId}
              onChange={setContactId}
              emptyLabel='Nobody'
              options={contacts.map((c) => ({
                value: String(c.id),
                label: c.name,
              }))}
            />
          </div>
          <div className='grid gap-1.5'>
            <Label>Ball in court when issued</Label>
            <Choice
              value={party}
              onChange={setParty}
              options={PARTIES.map((p) => ({ value: p, label: label(p) }))}
            />
          </div>
          <div className='grid gap-1.5'>
            <Label>Priority</Label>
            <Choice
              value={priority}
              onChange={setPriority}
              options={PRIORITIES.map((p) => ({ value: p, label: label(p) }))}
            />
          </div>
          <div className='grid gap-1.5'>
            <Label htmlFor='rfi-due'>Due date</Label>
            <Input id='rfi-due' name='due_date' type='date' />
            <span className='text-xs text-muted-foreground'>
              Leave empty for the project's default.
            </span>
          </div>
          <div className='grid gap-2'>
            <Label>Impact</Label>
            <div className='flex flex-wrap gap-4 text-sm'>
              {(
                [
                  ['cost_impact', 'Cost'],
                  ['schedule_impact', 'Schedule'],
                  ['scope_impact', 'Scope'],
                ] as [Impact, string][]
              ).map(([key, text]) => (
                <label key={key} className='flex items-center gap-1.5'>
                  <Checkbox
                    checked={impacts[key]}
                    onCheckedChange={(c) =>
                      setImpacts((s) => ({ ...s, [key]: c === true }))
                    }
                  />
                  {text}
                </label>
              ))}
            </div>
          </div>
          {impacts.cost_impact ? (
            <div className='grid gap-1.5'>
              <Label htmlFor='rfi-cost'>Estimated cost impact</Label>
              <Input
                id='rfi-cost'
                name='cost_amount'
                type='number'
                min={0}
                step='0.01'
              />
            </div>
          ) : null}
          {impacts.schedule_impact ? (
            <div className='grid gap-1.5'>
              <Label htmlFor='rfi-days'>Estimated delay (days)</Label>
              <Input id='rfi-days' name='days' type='number' min={0} />
            </div>
          ) : null}
        </form>
        <DialogFooter>
          <Button variant='outline' onClick={onClose}>
            Cancel
          </Button>
          <Button
            type='submit'
            form='rfi-create'
            variant='secondary'
            value='draft'
            disabled={create.isPending}
          >
            Save draft
          </Button>
          <Button
            type='submit'
            form='rfi-create'
            value='issue'
            disabled={create.isPending}
          >
            Issue
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
