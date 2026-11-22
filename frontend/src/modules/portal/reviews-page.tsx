import { useState } from 'react'
import { Download, Plus, Upload } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { useCurrentProject } from '@/stores/use-current-project'
import { can, useSession } from '@/lib/session'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Page } from '@/components/layout/page'
import { NativeSelect } from '@/components/native-select'
import { Field } from '@/components/records/fields'
import { uploadFile } from '@/components/records/files'
import { statusLabel } from '@/components/records/status'
import { StatusBadge } from '@/components/records/status-badge'
import {
  KINDS,
  type ReviewDetail,
  downloadUrl,
  useAddDocument,
  useComment,
  useCreateReview,
  useDecide,
  useReview,
  useReviews,
  useShare,
  useWithdraw,
} from './reviews-api'

async function upload(projectId: number, file: File) {
  const form = new FormData()
  form.append('file', file)
  form.append('project_id', String(projectId))
  form.append('entity_type', 'plan_review')
  return uploadFile(form)
}

function NewReview({
  projectId,
  onClose,
  onCreated,
}: {
  projectId: number
  onClose: () => void
  onCreated: (id: number) => void
}) {
  const { t } = useTranslation()
  const create = useCreateReview()
  const [title, setTitle] = useState('')
  const [kind, setKind] = useState('work_plan')
  const [due, setDue] = useState('')
  const [message, setMessage] = useState('')
  const [files, setFiles] = useState<File[]>([])
  const [busy, setBusy] = useState(false)
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className='sm:max-w-lg'>
        <DialogHeader>
          <DialogTitle>{t('reviews.new')}</DialogTitle>
        </DialogHeader>
        <Field label={t('reviews.title_field')}>
          <Input value={title} onChange={(e) => setTitle(e.target.value)} />
        </Field>
        <div className='grid grid-cols-2 gap-3'>
          <Field label={t('reviews.kind')}>
            <NativeSelect
              values={KINDS}
              value={kind}
              onChange={(e) => setKind(e.target.value)}
            />
          </Field>
          <Field label={t('reviews.due')}>
            <Input
              type='date'
              value={due}
              onChange={(e) => setDue(e.target.value)}
            />
          </Field>
        </div>
        <Field label={t('reviews.message')}>
          <Textarea
            value={message}
            onChange={(e) => setMessage(e.target.value)}
          />
        </Field>
        <Field label={t('reviews.documents')}>
          <Input
            type='file'
            multiple
            onChange={(e) => setFiles(Array.from(e.target.files ?? []))}
          />
        </Field>
        <DialogFooter>
          <Button
            disabled={!title || busy}
            onClick={async () => {
              setBusy(true)
              try {
                const uploaded = await Promise.all(
                  files.map((f) => upload(projectId, f))
                )
                create.mutate(
                  {
                    project_id: projectId,
                    title,
                    kind: kind as never,
                    due_date: due || null,
                    message: message || null,
                    documents: uploaded.map((f) => ({ file_id: f.id })),
                  },
                  {
                    onSuccess: (made) => {
                      onClose()
                      onCreated(made.id)
                    },
                  }
                )
              } catch (error) {
                toast.error(String(error))
              } finally {
                setBusy(false)
              }
            }}
          >
            {t('reviews.save_draft')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function Decision({
  review,
  documentId,
}: {
  review: ReviewDetail
  documentId: number
}) {
  const { t } = useTranslation()
  const decide = useDecide(review.id)
  const [comment, setComment] = useState('')
  const send = (decision: 'approved' | 'approved_with_comments' | 'rejected') =>
    decide.mutate({ documentId, decision, comment })
  return (
    <div className='grid gap-2'>
      <Textarea
        aria-label={t('reviews.decision_comment')}
        placeholder={t('reviews.decision_comment')}
        value={comment}
        onChange={(e) => setComment(e.target.value)}
      />
      <div className='flex flex-wrap gap-2'>
        <Button size='sm' onClick={() => send('approved')}>
          {t('reviews.approve')}
        </Button>
        <Button
          size='sm'
          variant='outline'
          disabled={!comment}
          onClick={() => send('approved_with_comments')}
        >
          {t('reviews.approve_with_comments')}
        </Button>
        <Button
          size='sm'
          variant='destructive'
          disabled={!comment}
          onClick={() => send('rejected')}
        >
          {t('reviews.reject')}
        </Button>
      </div>
    </div>
  )
}

function ReviewPanel({ id, projectId }: { id: number; projectId: number }) {
  const { t } = useTranslation()
  const session = useSession()
  const { data: review } = useReview(id)
  const share = useShare(id)
  const withdraw = useWithdraw(id)
  const addDocument = useAddDocument(id)
  const comment = useComment(id)
  const [body, setBody] = useState('')
  const [onDocument, setOnDocument] = useState('')
  if (!review) return null
  const canComment =
    can(session, 'portal.review') || can(session, 'portal.submit')
  return (
    <div className='grid gap-4 rounded-md border p-4'>
      <div className='flex flex-wrap items-center gap-2'>
        <h3 className='text-lg font-semibold'>
          {review.code} · {review.title}
        </h3>
        <StatusBadge status={review.status} />
        {review.outcome ? <StatusBadge status={review.outcome} /> : null}
        {review.overdue ? <StatusBadge status='overdue' /> : null}
        <span className='text-sm text-muted-foreground'>
          {statusLabel(review.kind)}
          {review.due_date ? ` · ${t('reviews.due')} ${review.due_date}` : ''}
          {review.client_team_name ? ` · ${review.client_team_name}` : ''}
        </span>
        {review.can_manage ? (
          <div className='ms-auto flex gap-2'>
            {review.status === 'draft' ? (
              <Button size='sm' onClick={() => share.mutate('')}>
                {t('reviews.share')}
              </Button>
            ) : null}
            {['draft', 'shared'].includes(review.status) ? (
              <Button
                size='sm'
                variant='outline'
                onClick={() => withdraw.mutate(undefined)}
              >
                {t('reviews.withdraw')}
              </Button>
            ) : null}
            {review.status !== 'withdrawn' ? (
              <Button size='sm' variant='outline' asChild>
                <label className='cursor-pointer'>
                  <Upload /> {t('reviews.add_document')}
                  <input
                    type='file'
                    className='hidden'
                    onChange={async (e) => {
                      const file = e.target.files?.[0]
                      if (!file) return
                      try {
                        const stored = await upload(projectId, file)
                        addDocument.mutate(stored.id)
                      } catch (error) {
                        toast.error(String(error))
                      }
                    }}
                  />
                </label>
              </Button>
            ) : null}
          </div>
        ) : null}
      </div>
      {review.message ? <p className='text-sm'>{review.message}</p> : null}
      <ul className='grid gap-3'>
        {review.documents.map((d) => (
          <li key={d.id} className='grid gap-2 rounded-md border p-3'>
            <div className='flex flex-wrap items-center gap-2'>
              <a
                className='flex items-center gap-1 font-medium underline'
                href={downloadUrl(review.id, d.id)}
              >
                <Download className='size-4' /> {d.title}
              </a>
              <StatusBadge status={d.decision} />
              {d.decided_by_name ? (
                <span className='text-xs text-muted-foreground'>
                  {d.decided_by_name}
                  {d.decided_at
                    ? ` · ${new Date(d.decided_at).toLocaleString()}`
                    : ''}
                </span>
              ) : null}
            </div>
            {d.decision_comment ? (
              <p className='text-sm'>{d.decision_comment}</p>
            ) : null}
            {review.can_decide ? (
              <Decision review={review} documentId={d.id} />
            ) : null}
          </li>
        ))}
      </ul>
      <section className='grid gap-2'>
        <h4 className='text-sm font-semibold'>{t('reviews.comments')}</h4>
        {review.comments.map((c) => (
          <div key={c.id} className='rounded-md bg-muted/50 p-2 text-sm'>
            <div className='text-xs text-muted-foreground'>
              {c.author_name}
              {c.from_client ? ` · ${t('reviews.client')}` : ''}
              {c.document_id
                ? ` · ${review.documents.find((d) => d.id === c.document_id)?.title ?? ''}`
                : ''}
              {c.created_at
                ? ` · ${new Date(c.created_at).toLocaleString()}`
                : ''}
            </div>
            <p>{c.body}</p>
          </div>
        ))}
        {canComment && review.status !== 'withdrawn' ? (
          <form
            className='grid gap-2'
            onSubmit={(e) => {
              e.preventDefault()
              comment.mutate(
                {
                  body,
                  documentId: onDocument ? Number(onDocument) : null,
                },
                { onSuccess: () => setBody('') }
              )
            }}
          >
            <Textarea
              aria-label={t('reviews.comment')}
              value={body}
              onChange={(e) => setBody(e.target.value)}
              required
            />
            <div className='flex gap-2'>
              <NativeSelect
                className='h-8'
                aria-label={t('reviews.on_document')}
                placeholder={t('reviews.whole_package')}
                options={review.documents.map((d) => ({
                  value: String(d.id),
                  label: d.title,
                }))}
                value={onDocument}
                onChange={(e) => setOnDocument(e.target.value)}
              />
              <Button size='sm' type='submit'>
                {t('reviews.comment')}
              </Button>
            </div>
          </form>
        ) : null}
      </section>
    </div>
  )
}

export default function ReviewsPage() {
  const { t } = useTranslation()
  const session = useSession()
  const project = useCurrentProject()
  const staff = can(session, 'portal.submit')
  const [status, setStatus] = useState(staff ? '' : 'shared')
  const [openId, setOpenId] = useState<number | null>(() => {
    const id = Number(new URLSearchParams(window.location.search).get('id'))
    return id > 0 ? id : null
  })
  const [creating, setCreating] = useState(false)
  const { data: rows = [] } = useReviews(project?.id ?? 0, status)
  return (
    <Page
      title={staff ? t('reviews.title') : t('reviews.queue')}
      description={
        staff ? t('reviews.description') : t('reviews.client_description')
      }
      projectScoped
      actions={
        project && staff ? (
          <Button size='sm' onClick={() => setCreating(true)}>
            <Plus /> {t('reviews.new')}
          </Button>
        ) : null
      }
    >
      {project ? (
        <div className='grid gap-4 lg:grid-cols-[22rem_1fr]'>
          <div className='grid content-start gap-2'>
            <NativeSelect
              className='h-8'
              aria-label={t('reviews.status')}
              placeholder={t('reviews.all')}
              values={['draft', 'shared', 'reviewed', 'withdrawn']}
              value={status}
              onChange={(e) => setStatus(e.target.value)}
            />
            {rows.map((r) => (
              <button
                key={r.id}
                type='button'
                onClick={() => setOpenId(r.id)}
                className='grid gap-1 rounded-md border p-2 text-start text-sm hover:bg-muted'
              >
                <span className='font-medium'>
                  {r.code} · {r.title}
                </span>
                <span className='flex flex-wrap items-center gap-1'>
                  <StatusBadge status={r.outcome ?? r.status} />
                  <span className='text-xs text-muted-foreground'>
                    {r.documents_decided}/{r.documents_total}{' '}
                    {t('reviews.decided')}
                    {r.due_date ? ` · ${t('reviews.due')} ${r.due_date}` : ''}
                  </span>
                  {r.overdue ? <StatusBadge status='overdue' /> : null}
                </span>
              </button>
            ))}
            {!rows.length ? (
              <p className='text-sm text-muted-foreground'>
                {t('reviews.none')}
              </p>
            ) : null}
          </div>
          {openId ? (
            <ReviewPanel key={openId} id={openId} projectId={project.id} />
          ) : null}
          {creating ? (
            <NewReview
              projectId={project.id}
              onClose={() => setCreating(false)}
              onCreated={setOpenId}
            />
          ) : null}
        </div>
      ) : (
        <p className='text-sm text-muted-foreground'>
          {t('reviews.no_project')}
        </p>
      )}
    </Page>
  )
}
