import { useRef, useState } from 'react'
import { Download, Eye, Upload } from 'lucide-react'
import { toast } from 'sonner'
import { can, useSession } from '@/lib/session'
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
import { Textarea } from '@/components/ui/textarea'
import { Comments } from '@/components/records/comments'
import { formatSize } from '@/components/records/files'
import { RecordSheet } from '@/components/records/record-sheet'
import { statusLabel } from '@/components/records/status'
import { StatusBadge } from '@/components/records/status-badge'
import {
  NEXT,
  STATES,
  SUITABILITY,
  downloadUrl,
  postForm,
  useChangeStatus,
  useDocument,
  useDocumentHistory,
  useRefresh,
  type CdeDocumentDetail,
  type CdeState,
} from './api'

const when = (value?: string | null) =>
  value ? new Date(value).toLocaleString() : ''

const stateLabel = (state: string) =>
  STATES.find((s) => s.id === state)?.label ?? statusLabel(state)

function TransitionDialog({
  doc,
  requireShareApproval,
  onClose,
}: {
  doc: CdeDocumentDetail
  requireShareApproval: boolean
  onClose: () => void
}) {
  const session = useSession()
  const change = useChangeStatus(doc.project_id)
  const targets = NEXT[doc.state as CdeState].filter(
    (s) => s !== 'archived' || can(session, 'cde.approve')
  )
  const [target, setTarget] = useState<CdeState>(targets[0])
  const codes = SUITABILITY[target] ?? {}
  const [suitability, setSuitability] = useState(Object.keys(codes)[0] ?? '')
  const [comment, setComment] = useState('')
  const gated =
    target === 'published' || (target === 'shared' && requireShareApproval)
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Change state of {doc.name}</DialogTitle>
        </DialogHeader>
        <div className='grid gap-3'>
          <div className='grid gap-1.5'>
            <Label>Move to</Label>
            <Select
              value={target}
              onValueChange={(v) => {
                setTarget(v as CdeState)
                setSuitability(Object.keys(SUITABILITY[v] ?? {})[0] ?? '')
              }}
            >
              <SelectTrigger className='w-full'>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {targets.map((s) => (
                  <SelectItem key={s} value={s}>
                    {stateLabel(s)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          {Object.keys(codes).length ? (
            <div className='grid gap-1.5'>
              <Label>Suitability</Label>
              <Select value={suitability} onValueChange={setSuitability}>
                <SelectTrigger className='w-full'>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {Object.entries(codes).map(([code, label]) => (
                    <SelectItem key={code} value={code}>
                      {code} · {label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          ) : null}
          <div className='grid gap-1.5'>
            <Label htmlFor='cde-comment'>Comment</Label>
            <Textarea
              id='cde-comment'
              value={comment}
              onChange={(e) => setComment(e.target.value)}
            />
          </div>
          {gated ? (
            <p className='text-xs text-muted-foreground'>
              {target === 'published'
                ? 'Publishing needs approval by someone holding CDE approve rights; the revision becomes the next C revision.'
                : "Sharing needs a task-team reviewer's check before it takes effect."}
            </p>
          ) : null}
        </div>
        <DialogFooter>
          <Button
            disabled={change.isPending || !target}
            onClick={() =>
              change.mutate(
                {
                  id: doc.id,
                  body: {
                    state: target,
                    suitability: suitability || undefined,
                    comment: comment || null,
                  },
                },
                {
                  onSuccess: () => {
                    toast.success(
                      gated ? 'Approval requested' : 'State changed'
                    )
                    onClose()
                  },
                }
              )
            }
          >
            {gated ? 'Request approval' : 'Change state'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function Decide({ doc }: { doc: CdeDocumentDetail }) {
  const change = useChangeStatus(doc.project_id)
  const [comment, setComment] = useState('')
  const decide = (decision: 'approve' | 'reject') =>
    change.mutate(
      { id: doc.id, body: { decision, comment: comment || null } },
      {
        onSuccess: () =>
          toast.success(decision === 'approve' ? 'Approved' : 'Rejected'),
      }
    )
  return (
    <div className='grid gap-2 rounded-md border border-amber-500/40 bg-amber-500/5 p-3'>
      <p className='text-sm'>
        <strong>{doc.requested_by_name ?? 'Someone'}</strong> asks to make this{' '}
        <strong>{stateLabel(doc.pending_state ?? '')}</strong> as{' '}
        <strong>{doc.pending_suitability}</strong>
        <span className='text-xs text-muted-foreground'>
          {' '}
          · {when(doc.requested_at)}
        </span>
      </p>
      {doc.request_comment ? (
        <p className='text-xs text-muted-foreground'>“{doc.request_comment}”</p>
      ) : null}
      {doc.can_decide ? (
        <>
          <Textarea
            placeholder='Comment for the requester'
            value={comment}
            onChange={(e) => setComment(e.target.value)}
          />
          <div className='flex gap-2'>
            <Button
              size='sm'
              disabled={change.isPending}
              onClick={() => decide('approve')}
            >
              Approve
            </Button>
            <Button
              size='sm'
              variant='outline'
              disabled={change.isPending}
              onClick={() => decide('reject')}
            >
              Reject
            </Button>
          </div>
        </>
      ) : (
        <p className='text-xs text-muted-foreground'>
          Waiting for an approver.
        </p>
      )}
    </div>
  )
}

function Revisions({ doc }: { doc: CdeDocumentDetail }) {
  return (
    <div className='grid gap-2'>
      {(doc.revisions ?? []).map((r) => (
        <div
          key={r.id}
          className='flex items-center gap-3 rounded-md border px-3 py-2 text-sm'
        >
          <span className='w-10 font-mono font-semibold'>{r.code}</span>
          <StatusBadge status={r.superseded ? 'superseded' : r.state} />
          <span className='text-xs text-muted-foreground'>{r.suitability}</span>
          <span className='flex-1 truncate'>
            {r.file_name}
            {r.file_size ? (
              <span className='text-xs text-muted-foreground'>
                {' '}
                · {formatSize(r.file_size)}
              </span>
            ) : null}
            <span className='block text-xs text-muted-foreground'>
              {r.created_by_name} · {when(r.created_at)}
              {r.comment ? ` · ${r.comment}` : ''}
            </span>
          </span>
          {r.file_id ? (
            <>
              <a
                href={downloadUrl(doc.id, r.id, true)}
                target='_blank'
                rel='noreferrer'
                aria-label='Preview'
              >
                <Eye className='size-4' />
              </a>
              <a href={downloadUrl(doc.id, r.id)} aria-label='Download'>
                <Download className='size-4' />
              </a>
            </>
          ) : null}
        </div>
      ))}
    </div>
  )
}

function Timeline({ id }: { id: number }) {
  const { data = [] } = useDocumentHistory(id)
  return (
    <ol className='grid gap-3 border-s ps-4'>
      {data.map((h, i) => (
        <li key={i} className='relative grid gap-0.5 text-sm'>
          <span className='absolute -start-[21px] top-1.5 size-2.5 rounded-full bg-primary' />
          <span className='flex flex-wrap items-center gap-2'>
            {h.from_status && h.from_status !== h.to_status ? (
              <>
                <StatusBadge status={h.from_status} />→
              </>
            ) : null}
            <StatusBadge status={h.to_status} />
          </span>
          <span className='text-xs text-muted-foreground'>
            {h.changed_by_name ?? 'System'} · {when(h.changed_at)}
          </span>
          {h.note ? <span className='text-xs'>{h.note}</span> : null}
        </li>
      ))}
    </ol>
  )
}

export function DocumentSheet({
  id,
  requireShareApproval,
  onClose,
}: {
  id: number | null
  requireShareApproval: boolean
  onClose: () => void
}) {
  const session = useSession()
  const { data: doc } = useDocument(id)
  const refresh = useRefresh(doc?.project_id ?? 0)
  const input = useRef<HTMLInputElement>(null)
  const [transition, setTransition] = useState(false)
  const [uploading, setUploading] = useState(false)
  if (id === null || !doc) return null

  const newRevision = async (file: File) => {
    setUploading(true)
    try {
      const form = new FormData()
      form.set('file', file)
      const updated = await postForm(
        `/api/v1/cde/documents/${doc.id}/revisions`,
        form
      )
      toast.success(`Revision ${updated.revision} uploaded`)
      refresh()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Upload failed')
    } finally {
      setUploading(false)
    }
  }

  const canTransition =
    can(session, 'cde.transition') &&
    !doc.pending_state &&
    NEXT[doc.state as CdeState].length > 0
  const canRevise =
    can(session, 'cde.upload') && !doc.pending_state && doc.state !== 'archived'

  return (
    <>
      <RecordSheet
        open
        wide
        onClose={onClose}
        title={<span className='font-mono'>{doc.name}</span>}
        subtitle={doc.title}
        badges={
          <>
            <StatusBadge status={doc.state} />
            <StatusBadge status={doc.suitability} />
            <StatusBadge status={doc.revision} />
            {doc.pending_state ? <StatusBadge status='pending' /> : null}
          </>
        }
        tabs={{
          Revisions: <Revisions doc={doc} />,
          History: <Timeline id={doc.id} />,
          Comments: (
            <Comments
              projectId={doc.project_id}
              entityType='cde_document'
              entityId={doc.id}
            />
          ),
        }}
      >
        <div className='grid gap-4'>
          <div className='flex flex-wrap gap-2'>
            <Button size='sm' variant='outline' asChild>
              <a href={downloadUrl(doc.id)}>
                <Download /> Download {doc.revision}
              </a>
            </Button>
            {canTransition ? (
              <Button size='sm' onClick={() => setTransition(true)}>
                Change state
              </Button>
            ) : null}
            {canRevise ? (
              <>
                <input
                  ref={input}
                  type='file'
                  hidden
                  onChange={(e) => {
                    const file = e.target.files?.[0]
                    if (file) void newRevision(file)
                    e.target.value = ''
                  }}
                />
                <Button
                  size='sm'
                  variant='outline'
                  disabled={uploading}
                  onClick={() => input.current?.click()}
                >
                  <Upload /> New revision
                </Button>
              </>
            ) : null}
          </div>
          {doc.pending_state ? <Decide doc={doc} /> : null}
          <div className='grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-4'>
            {Object.entries(doc.fields).map(([key, value]) => (
              <div key={key} className='grid gap-0.5'>
                <span className='text-xs text-muted-foreground'>
                  {statusLabel(key)}
                </span>
                <span className='font-mono text-sm'>{value}</span>
              </div>
            ))}
          </div>
          <div className='grid gap-1 text-sm'>
            <span>
              <span className='text-muted-foreground'>File: </span>
              {doc.file_name}
            </span>
            <span>
              <span className='text-muted-foreground'>Author: </span>
              {doc.created_by_name}
            </span>
            <span>
              <span className='text-muted-foreground'>Suitability: </span>
              {doc.suitability} ·{' '}
              {SUITABILITY[doc.state]?.[doc.suitability] ?? ''}
            </span>
          </div>
          {doc.description ? (
            <p className='text-sm whitespace-pre-wrap'>{doc.description}</p>
          ) : null}
        </div>
      </RecordSheet>
      {transition ? (
        <TransitionDialog
          doc={doc}
          requireShareApproval={requireShareApproval}
          onClose={() => setTransition(false)}
        />
      ) : null}
    </>
  )
}
