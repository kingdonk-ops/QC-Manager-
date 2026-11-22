import { useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ListTodo, Paperclip, Upload } from 'lucide-react'
import { toast } from 'sonner'
import { api, unwrap } from '@/api/client'
import { handleServerError } from '@/lib/handle-server-error'
import { can, useSession } from '@/lib/session'
import { cn } from '@/lib/utils'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import {
  fileUrl,
  uploadFile,
  type StoredFile,
} from '@/components/records/files'
import { RecordSheet } from '@/components/records/record-sheet'
import { StatusBadge } from '@/components/records/status-badge'
import {
  NEXT,
  PARTIES,
  label,
  rfiKeys,
  useContactOptions,
  useRfiHistory,
  useRfiUsers,
  type RfiDetail,
} from './api'
import { Choice } from './choice'

function Field({ name, value }: { name: string; value: React.ReactNode }) {
  return (
    <div className='grid gap-0.5'>
      <span className='text-xs text-muted-foreground'>{name}</span>
      <span className='text-sm'>{value || '—'}</span>
    </div>
  )
}

function useRfiMutation<T>(
  rfi: RfiDetail,
  fn: (body: T) => Promise<RfiDetail>,
  done?: string
) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSuccess: (data) => {
      queryClient.setQueryData(rfiKeys.one(rfi.id), data)
      void queryClient.invalidateQueries({
        queryKey: rfiKeys.all(rfi.project_id),
      })
      void queryClient.invalidateQueries({ queryKey: rfiKeys.history(rfi.id) })
      if (done) toast.success(done)
    },
    onError: handleServerError,
  })
}

function Controls({ rfi }: { rfi: RfiDetail }) {
  const session = useSession()
  const { data: users = [] } = useRfiUsers()
  const { data: contacts = [] } = useContactOptions()
  const [party, setParty] = useState(rfi.ball_in_court ?? 'designer')
  const [userId, setUserId] = useState(
    rfi.bic_user_id ? String(rfi.bic_user_id) : ''
  )
  const [contactId, setContactId] = useState(
    rfi.bic_contact_id ? String(rfi.bic_contact_id) : ''
  )
  const change = useRfiMutation(
    rfi,
    (body: Record<string, unknown>) =>
      unwrap(
        api.PATCH('/api/v1/rfis/{rfi_id}/status', {
          params: { path: { rfi_id: rfi.id } },
          body: body as never,
        })
      ),
    'Updated'
  )
  const task = useMutation({
    mutationFn: () =>
      unwrap(
        api.POST('/api/v1/rfis/{rfi_id}/task', {
          params: { path: { rfi_id: rfi.id } },
          body: {},
        })
      ),
    onSuccess: (t) => toast.success(`${t.code} created`),
    onError: handleServerError,
  })
  if (!can(session, 'rfi.transition')) return null
  return (
    <div className='grid gap-3 rounded-md border p-3'>
      <div className='flex flex-wrap items-center gap-2'>
        <span className='text-sm font-medium'>Move to</span>
        {(NEXT[rfi.status] ?? []).map((s) => (
          <Button
            key={s}
            size='sm'
            variant={s === 'void' ? 'ghost' : 'outline'}
            disabled={change.isPending}
            onClick={() => change.mutate({ status: s })}
          >
            {label(s)}
          </Button>
        ))}
        {can(session, 'tasks.create') && can(session, 'rfi.update') ? (
          <Button
            size='sm'
            variant='ghost'
            className='ms-auto'
            disabled={task.isPending}
            onClick={() => task.mutate()}
          >
            <ListTodo /> Create task
          </Button>
        ) : null}
      </div>
      <div className='grid grid-cols-3 gap-2'>
        <div className='grid gap-1'>
          <Label className='text-xs'>Ball in court</Label>
          <Choice
            value={party}
            onChange={setParty}
            options={PARTIES.map((p) => ({ value: p, label: label(p) }))}
          />
        </div>
        <div className='grid gap-1'>
          <Label className='text-xs'>User to act</Label>
          <Choice
            value={userId}
            onChange={setUserId}
            emptyLabel='Nobody'
            options={users.map((u) => ({ value: String(u.id), label: u.name }))}
          />
        </div>
        <div className='grid gap-1'>
          <Label className='text-xs'>Contact to act</Label>
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
      </div>
      <Button
        size='sm'
        variant='secondary'
        className='w-fit'
        disabled={change.isPending}
        onClick={() =>
          change.mutate({
            ball_in_court: party,
            bic_user_id: userId ? Number(userId) : null,
            bic_contact_id: contactId ? Number(contactId) : null,
          })
        }
      >
        Hand over
      </Button>
    </div>
  )
}

function Details({ rfi }: { rfi: RfiDetail }) {
  const impacts = (
    [
      ['cost_impact', 'Cost'],
      ['schedule_impact', 'Schedule'],
      ['scope_impact', 'Scope'],
    ] as const
  ).filter(([k]) => rfi[k])
  return (
    <div className='grid gap-4'>
      <div className='grid gap-1'>
        <span className='text-xs text-muted-foreground'>Question</span>
        <p className='text-sm whitespace-pre-wrap'>{rfi.question}</p>
      </div>
      <div className='grid grid-cols-2 gap-3'>
        <Field
          name='Ball in court'
          value={
            rfi.ball_in_court
              ? `${label(rfi.ball_in_court)}${
                  rfi.bic_user_name || rfi.bic_contact_name
                    ? ` · ${rfi.bic_user_name ?? rfi.bic_contact_name}`
                    : ''
                }`
              : null
          }
        />
        <Field
          name='Due'
          value={
            rfi.due_date ? (
              <span className={cn(rfi.overdue && 'font-medium text-red-600')}>
                {rfi.due_date}
                {rfi.overdue ? ' (overdue)' : ''}
              </span>
            ) : null
          }
        />
        <Field
          name='Raised by'
          value={`${rfi.raised_by_name ?? '—'} · ${label(rfi.raised_by_party)}`}
        />
        <Field
          name='Addressed to'
          value={[rfi.addressed_to_user_name, rfi.addressed_to_contact_name]
            .filter(Boolean)
            .join(', ')}
        />
        <Field name='Discipline' value={rfi.discipline} />
        <Field name='Location' value={rfi.location} />
        <Field
          name='Days open'
          value={rfi.days_open !== null ? String(rfi.days_open) : null}
        />
        <Field
          name='Linked record'
          value={
            rfi.entity_type
              ? `${label(rfi.entity_type)} #${rfi.entity_id}`
              : null
          }
        />
        <Field
          name='Impact'
          value={
            impacts.length ? (
              <span className='flex flex-wrap gap-1'>
                {impacts.map(([k, text]) => (
                  <Badge key={k} variant='secondary'>
                    {text}
                  </Badge>
                ))}
                {rfi.cost_impact_amount ? ` ${rfi.cost_impact_amount}` : ''}
                {rfi.schedule_impact_days
                  ? ` · ${rfi.schedule_impact_days} days`
                  : ''}
              </span>
            ) : (
              'None'
            )
          }
        />
      </div>
      <Controls key={`${rfi.status}-${rfi.bic_user_id}`} rfi={rfi} />
    </div>
  )
}

function Responses({ rfi }: { rfi: RfiDetail }) {
  const session = useSession()
  const input = useRef<HTMLInputElement>(null)
  const [body, setBody] = useState('')
  const [answer, setAnswer] = useState(true)
  const [files, setFiles] = useState<StoredFile[]>([])
  const [uploading, setUploading] = useState(false)
  const respond = useRfiMutation(
    rfi,
    () =>
      unwrap(
        api.POST('/api/v1/rfis/{rfi_id}/respond', {
          params: { path: { rfi_id: rfi.id } },
          body: {
            body,
            is_answer: answer,
            attachment_ids: files.map((f) => f.id),
          },
        })
      ),
    'Response added'
  )
  const attach = async (list: FileList) => {
    setUploading(true)
    try {
      for (const file of Array.from(list)) {
        const form = new FormData()
        form.set('file', file)
        form.set('project_id', String(rfi.project_id))
        form.set('category', 'correspondence')
        const stored = await uploadFile(form)
        setFiles((f) => [...f, stored])
      }
    } catch (e) {
      handleServerError(e)
    } finally {
      setUploading(false)
    }
  }
  const canRespond =
    can(session, 'rfi.respond') && ['open', 'answered'].includes(rfi.status)

  return (
    <div className='grid gap-3'>
      {rfi.responses?.length ? null : (
        <p className='text-sm text-muted-foreground'>No responses yet.</p>
      )}
      {rfi.responses?.map((r, i) => (
        <div
          key={r.id}
          className={cn(
            'grid gap-1 rounded-md border p-3',
            r.is_answer && 'border-green-500/40 bg-green-500/5'
          )}
        >
          <div className='flex items-center gap-2 text-xs text-muted-foreground'>
            <span className='font-medium text-foreground'>
              {r.author_name ?? 'Former user'}
            </span>
            {r.created_at ? new Date(r.created_at).toLocaleString() : null}
            <span>· round {i + 1}</span>
            {r.is_answer ? <StatusBadge status='answered' /> : null}
          </div>
          <p className='text-sm whitespace-pre-wrap'>{r.body}</p>
          {r.attachments?.map((a) => (
            <a
              key={a.id}
              href={fileUrl(a.id)}
              className='flex items-center gap-1 text-xs underline'
            >
              <Paperclip className='size-3' /> {a.name}
            </a>
          ))}
        </div>
      ))}
      {canRespond ? (
        <div className='grid gap-2'>
          <Textarea
            rows={4}
            placeholder='Write a response'
            value={body}
            onChange={(e) => setBody(e.target.value)}
          />
          <div className='flex flex-wrap items-center gap-3 text-sm'>
            <label className='flex items-center gap-1.5'>
              <Checkbox
                checked={answer}
                onCheckedChange={(c) => setAnswer(c === true)}
              />
              This answers the question
            </label>
            <input
              ref={input}
              type='file'
              multiple
              hidden
              onChange={(e) => e.target.files?.length && attach(e.target.files)}
            />
            {can(session, 'files.upload') ? (
              <Button
                size='sm'
                variant='outline'
                disabled={uploading}
                onClick={() => input.current?.click()}
              >
                <Upload /> Attach
              </Button>
            ) : null}
            {files.map((f) => (
              <Badge key={f.id} variant='secondary'>
                {f.name}
              </Badge>
            ))}
            <Button
              size='sm'
              className='ms-auto'
              disabled={!body.trim() || respond.isPending || uploading}
              onClick={() =>
                respond.mutate(undefined, {
                  onSuccess: () => {
                    setBody('')
                    setFiles([])
                  },
                })
              }
            >
              Send response
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  )
}

function History({ id }: { id: number }) {
  const { data = [] } = useRfiHistory(id)
  return (
    <ol className='grid gap-2'>
      {data.map((h, i) => (
        <li key={i} className='flex flex-wrap items-center gap-2 text-sm'>
          <StatusBadge status={h.to_status} />
          <span className='text-muted-foreground'>
            {h.changed_at ? new Date(h.changed_at).toLocaleString() : ''}
            {h.changed_by_name ? ` · ${h.changed_by_name}` : ''}
          </span>
          {h.note ? <span className='italic'>“{h.note}”</span> : null}
        </li>
      ))}
    </ol>
  )
}

/** One RFI: question and controls, the response thread, history, comments and files. */
export function RfiSheet({ id, onClose }: { id: number; onClose: () => void }) {
  const { data: rfi } = useQuery({
    queryKey: rfiKeys.one(id),
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/rfis/{rfi_id}', { params: { path: { rfi_id: id } } })
      ),
  })
  return (
    <RecordSheet
      open
      wide
      onClose={onClose}
      title={rfi ? `${rfi.code} · ${rfi.subject}` : 'Loading…'}
      badges={
        rfi ? (
          <>
            <StatusBadge status={rfi.status} />
            <StatusBadge status={rfi.priority} />
            {rfi.overdue ? <StatusBadge status='overdue' /> : null}
          </>
        ) : null
      }
      record={
        rfi
          ? { projectId: rfi.project_id, entityType: 'rfi', entityId: rfi.id }
          : undefined
      }
      tabs={
        rfi
          ? {
              Responses: <Responses rfi={rfi} />,
              History: <History id={rfi.id} />,
            }
          : undefined
      }
    >
      {rfi ? <Details rfi={rfi} /> : null}
    </RecordSheet>
  )
}
