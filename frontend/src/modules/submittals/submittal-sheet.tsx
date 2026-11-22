import { useState } from 'react'
import { Check, Clock, Download, Eye, Minus, X } from 'lucide-react'
import { toast } from 'sonner'
import { can, useSession } from '@/lib/session'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import { Attachments } from '@/components/records/attachments'
import { fileUrl, formatSize, uploadFile } from '@/components/records/files'
import { RecordSheet } from '@/components/records/record-sheet'
import { statusLabel } from '@/components/records/status'
import { StatusBadge } from '@/components/records/status-badge'
import {
  DECISIONS,
  typeLabel,
  useAction,
  useHistory,
  useRevisions,
  useSubmittal,
  type Decision,
  type Review,
  type SubmittalDetail,
} from './api'

const REVISABLE = ['approved_as_noted', 'revise_and_resubmit', 'rejected']
const CLOSABLE = ['approved', 'approved_as_noted', 'rejected']

const when = (value?: string | null) =>
  value ? new Date(value).toLocaleString() : ''

function Field({
  label,
  children,
}: {
  label: string
  children: React.ReactNode
}) {
  return (
    <div className='grid gap-0.5'>
      <span className='text-xs text-muted-foreground'>{label}</span>
      <span className='text-sm'>{children || '—'}</span>
    </div>
  )
}

function DecisionIcon({ review }: { review: Review }) {
  if (review.state === 'skipped')
    return <Minus className='size-4 text-muted-foreground' />
  if (review.state === 'open') return <Clock className='size-4 text-blue-600' />
  if (review.state === 'pending')
    return <Clock className='size-4 text-muted-foreground' />
  if (
    review.decision === 'rejected' ||
    review.decision === 'revise_and_resubmit'
  )
    return <X className='size-4 text-red-600' />
  return <Check className='size-4 text-green-600' />
}

/** The workflow as a vertical stepper, each reviewer with their decision stamp. */
export function Stepper({ reviews }: { reviews: Review[] }) {
  const steps = new Map<number, Review[]>()
  for (const r of reviews) steps.set(r.step, [...(steps.get(r.step) ?? []), r])
  if (steps.size === 0)
    return (
      <p className='text-sm text-muted-foreground'>
        The review starts when the submittal is submitted.
      </p>
    )
  return (
    <ol className='grid gap-3'>
      {[...steps.entries()].map(([step, members]) => {
        const open = members.some((m) => m.state === 'open')
        return (
          <li key={step} className='flex gap-3'>
            <span
              className={cn(
                'flex size-6 shrink-0 items-center justify-center rounded-full border text-xs font-semibold',
                open && 'border-blue-600 text-blue-600'
              )}
            >
              {step + 1}
            </span>
            <div className='grid flex-1 gap-1.5'>
              <div className='text-sm font-medium'>
                {members[0].step_name}
                {members[0].parallel ? (
                  <span className='ms-2 text-xs font-normal text-muted-foreground'>
                    parallel
                  </span>
                ) : null}
              </div>
              {members.map((m) => (
                <div
                  key={m.id}
                  className='flex items-start gap-2 rounded-md border px-3 py-2 text-sm'
                >
                  <DecisionIcon review={m} />
                  <div className='grid flex-1 gap-0.5'>
                    <div className='flex flex-wrap items-center gap-2'>
                      <span>{m.reviewer_name ?? 'Unknown'}</span>
                      {m.decision ? (
                        <StatusBadge status={m.decision} />
                      ) : (
                        <span className='text-xs text-muted-foreground'>
                          {statusLabel(m.state)}
                        </span>
                      )}
                      {m.decided_at ? (
                        <span className='text-xs text-muted-foreground'>
                          {when(m.decided_at)}
                        </span>
                      ) : null}
                    </div>
                    {m.comment ? (
                      <p className='text-xs whitespace-pre-wrap text-muted-foreground'>
                        “{m.comment}”
                      </p>
                    ) : null}
                  </div>
                </div>
              ))}
            </div>
          </li>
        )
      })}
    </ol>
  )
}

function ReviewDialog({
  submittal,
  onClose,
}: {
  submittal: SubmittalDetail
  onClose: () => void
}) {
  const review = useAction(submittal.project_id, 'review')
  const [decision, setDecision] = useState<Decision>('approved')
  const [comment, setComment] = useState('')
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            Review {submittal.code} Rev {submittal.revision_letter}
          </DialogTitle>
        </DialogHeader>
        <div className='grid gap-3'>
          <div className='grid gap-1.5'>
            <Label>Decision</Label>
            <Select
              value={decision}
              onValueChange={(v) => setDecision(v as Decision)}
            >
              <SelectTrigger className='w-full'>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {DECISIONS.map((d) => (
                  <SelectItem key={d} value={d}>
                    {statusLabel(d)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {decision === 'revise_and_resubmit' || decision === 'rejected' ? (
              <p className='text-xs text-muted-foreground'>
                This ends the review now; later steps won't be asked.
              </p>
            ) : null}
          </div>
          <div className='grid gap-1.5'>
            <Label htmlFor='review-comment'>Comment (stamped)</Label>
            <Textarea
              id='review-comment'
              value={comment}
              onChange={(e) => setComment(e.target.value)}
            />
          </div>
        </div>
        <DialogFooter>
          <Button
            disabled={review.isPending}
            onClick={() =>
              review.mutate(
                {
                  id: submittal.id,
                  body: { decision, comment: comment || null },
                },
                {
                  onSuccess: () => {
                    toast.success('Decision recorded')
                    onClose()
                  },
                }
              )
            }
          >
            Record decision
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function ReviseDialog({
  submittal,
  onClose,
}: {
  submittal: SubmittalDetail
  onClose: () => void
}) {
  const revise = useAction(submittal.project_id, 'revise')
  const [note, setNote] = useState('')
  const [files, setFiles] = useState<FileList | null>(null)
  const [submitNow, setSubmitNow] = useState(true)
  const [busy, setBusy] = useState(false)
  const next = String.fromCharCode(
    submittal.revision_letter.charCodeAt(submittal.revision_letter.length - 1) +
      1
  )
  const go = async () => {
    setBusy(true)
    try {
      const ids: number[] = []
      for (const file of Array.from(files ?? [])) {
        const form = new FormData()
        form.set('file', file)
        ids.push((await uploadFile(form)).id)
      }
      revise.mutate(
        {
          id: submittal.id,
          body: { note: note || null, file_ids: ids, submit: submitNow },
        },
        {
          onSuccess: () => {
            toast.success('New revision started')
            onClose()
          },
        }
      )
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Upload failed')
    } finally {
      setBusy(false)
    }
  }
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            Revise {submittal.code} (Rev{' '}
            {submittal.revision_letter.length === 1 && next <= 'Z'
              ? next
              : 'next'}
            )
          </DialogTitle>
        </DialogHeader>
        <div className='grid gap-3'>
          <div className='grid gap-1.5'>
            <Label htmlFor='revise-files'>Files for the new revision</Label>
            <input
              id='revise-files'
              type='file'
              multiple
              className='text-sm'
              onChange={(e) => setFiles(e.target.files)}
            />
          </div>
          <div className='grid gap-1.5'>
            <Label htmlFor='revise-note'>What changed</Label>
            <Textarea
              id='revise-note'
              value={note}
              onChange={(e) => setNote(e.target.value)}
            />
          </div>
          <Label className='flex items-center gap-2 font-normal'>
            <Switch checked={submitNow} onCheckedChange={setSubmitNow} />
            Submit for review now (the workflow starts again from step 1)
          </Label>
        </div>
        <DialogFooter>
          <Button disabled={busy || revise.isPending} onClick={() => void go()}>
            Start revision
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function Revisions({ submittal }: { submittal: SubmittalDetail }) {
  const { data: revisions = [] } = useRevisions(submittal.id)
  const editable =
    can(useSession(), 'files.upload') && submittal.current_revision_id
  return (
    <div className='grid gap-3'>
      {editable && submittal.status === 'draft' ? (
        <div className='grid gap-2 rounded-md border border-dashed p-3'>
          <span className='text-sm font-medium'>
            Files for Rev {submittal.revision_letter}
          </span>
          <Attachments
            projectId={submittal.project_id}
            entityType='submittal_revision'
            entityId={submittal.current_revision_id!}
          />
        </div>
      ) : null}
      <div className='grid gap-3 md:grid-cols-2'>
        {revisions.map((rev) => (
          <div
            key={rev.id}
            className='grid content-start gap-2 rounded-md border p-3'
          >
            <div className='flex items-center gap-2'>
              <span className='text-sm font-semibold'>Rev {rev.letter}</span>
              <StatusBadge status={rev.outcome ?? 'in review'} />
              <span className='ms-auto text-xs text-muted-foreground'>
                {when(rev.submitted_at) || 'not submitted'}
              </span>
            </div>
            {rev.note ? (
              <p className='text-xs text-muted-foreground'>{rev.note}</p>
            ) : null}
            <div className='grid gap-1'>
              {rev.files.length === 0 ? (
                <span className='text-xs text-muted-foreground'>No files</span>
              ) : null}
              {rev.files.map((f) => (
                <div key={f.id} className='flex items-center gap-2 text-sm'>
                  <span className='flex-1 truncate'>
                    {f.name}
                    <span className='text-xs text-muted-foreground'>
                      {' '}
                      · {formatSize(f.size)}
                    </span>
                  </span>
                  <a
                    href={fileUrl(f.id, true)}
                    target='_blank'
                    rel='noreferrer'
                    aria-label='Preview'
                  >
                    <Eye className='size-4' />
                  </a>
                  <a href={fileUrl(f.id)} aria-label='Download'>
                    <Download className='size-4' />
                  </a>
                </div>
              ))}
            </div>
            <div className='grid gap-1 border-t pt-2'>
              {rev.reviews.map((r) => (
                <div key={r.id} className='flex items-center gap-2 text-xs'>
                  <DecisionIcon review={r} />
                  <span>{r.reviewer_name}</span>
                  <span className='text-muted-foreground'>
                    {r.decision
                      ? statusLabel(r.decision)
                      : statusLabel(r.state)}
                  </span>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

function History({ id }: { id: number }) {
  const { data = [] } = useHistory(id)
  return (
    <ol className='grid gap-2 border-s ps-4'>
      {data.map((h, i) => (
        <li key={i} className='grid gap-0.5 text-sm'>
          <span>
            <StatusBadge status={h.to_status} />{' '}
            <span className='text-xs text-muted-foreground'>
              {h.changed_by_name ?? ''} · {when(h.changed_at)}
            </span>
          </span>
          {h.note ? (
            <span className='text-xs text-muted-foreground'>{h.note}</span>
          ) : null}
        </li>
      ))}
    </ol>
  )
}

export function SubmittalSheet({
  id,
  onClose,
}: {
  id: number | null
  onClose: () => void
}) {
  const session = useSession()
  const { data: s } = useSubmittal(id)
  const [dialog, setDialog] = useState<'review' | 'revise' | null>(null)
  const submit = useAction(s?.project_id ?? 0, 'submit')
  const close = useAction(s?.project_id ?? 0, 'close')
  if (id === null || !s) return null
  return (
    <>
      <RecordSheet
        open
        wide
        onClose={onClose}
        title={`${s.code} · ${s.title}`}
        subtitle={`${typeLabel(s.type)}${s.spec_section ? ` · Spec ${s.spec_section}` : ''}`}
        badges={
          <>
            <StatusBadge status={s.status} />
            <StatusBadge status={`Rev ${s.revision_letter}`} />
            {s.overdue ? <StatusBadge status='overdue' /> : null}
          </>
        }
        record={{
          projectId: s.project_id,
          entityType: 'submittal',
          entityId: s.id,
        }}
        tabs={{
          Revisions: <Revisions submittal={s} />,
          History: <History id={s.id} />,
        }}
      >
        <div className='grid gap-4'>
          <div className='flex flex-wrap gap-2'>
            {s.status === 'draft' && can(session, 'submittals.submit') ? (
              <Button
                size='sm'
                disabled={submit.isPending}
                onClick={() =>
                  submit.mutate(
                    { id: s.id, body: {} },
                    { onSuccess: () => toast.success('Submitted for review') }
                  )
                }
              >
                Submit for review
              </Button>
            ) : null}
            {s.my_open_review_id ? (
              <Button size='sm' onClick={() => setDialog('review')}>
                Review
              </Button>
            ) : null}
            {REVISABLE.includes(s.status) &&
            can(session, 'submittals.submit') ? (
              <Button
                size='sm'
                variant='outline'
                onClick={() => setDialog('revise')}
              >
                Revise and resubmit
              </Button>
            ) : null}
            {CLOSABLE.includes(s.status) &&
            can(session, 'submittals.update') ? (
              <Button
                size='sm'
                variant='outline'
                onClick={() => close.mutate({ id: s.id, body: {} })}
              >
                Close
              </Button>
            ) : null}
          </div>
          <div className='grid grid-cols-2 gap-3'>
            <Field label='Submitted by'>{s.submitted_by_name}</Field>
            <Field label='Required by'>{s.required_by}</Field>
            <Field label='Current reviewers'>
              {(s.current_reviewers ?? []).join(', ')}
            </Field>
            <Field label='Days outstanding'>{s.days_outstanding ?? ''}</Field>
            {s.entity_type ? (
              <Field label='Linked record'>
                {statusLabel(s.entity_type)} #{s.entity_id}
              </Field>
            ) : null}
          </div>
          {s.description ? (
            <p className='text-sm whitespace-pre-wrap'>{s.description}</p>
          ) : null}
          <div className='grid gap-2'>
            <span className='text-sm font-semibold'>
              Review workflow · Rev {s.revision_letter}
            </span>
            <Stepper reviews={s.reviews ?? []} />
          </div>
        </div>
      </RecordSheet>
      {dialog === 'review' ? (
        <ReviewDialog submittal={s} onClose={() => setDialog(null)} />
      ) : null}
      {dialog === 'revise' ? (
        <ReviseDialog submittal={s} onClose={() => setDialog(null)} />
      ) : null}
    </>
  )
}
