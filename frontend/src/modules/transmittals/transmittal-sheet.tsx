import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, FileText, Send, Trash2 } from 'lucide-react'
import { toast } from 'sonner'
import { api, unwrap } from '@/api/client'
import { handleServerError } from '@/lib/handle-server-error'
import { can, useSession } from '@/lib/session'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { ConfirmDialog } from '@/components/confirm-dialog'
import { RecordSheet } from '@/components/records/record-sheet'
import { StatusBadge } from '@/components/records/status-badge'
import {
  coverUrl,
  label,
  trKeys,
  useTransmittal,
  type Recipient,
  type Transmittal,
} from './api'
import { ContactPicker, DocumentPicker } from './pickers'

type HistoryEntry = {
  to_status: string
  changed_by_name?: string | null
  note?: string | null
  changed_at: string | null
}

function useTransmittalMutation<T>(
  t: Transmittal,
  fn: (arg: T) => Promise<Transmittal>,
  done?: string
) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSuccess: (data) => {
      queryClient.setQueryData(trKeys.one(t.id), data)
      void queryClient.invalidateQueries({
        queryKey: trKeys.all(t.project_id),
      })
      void queryClient.invalidateQueries({
        queryKey: ['transmittals', 'history', t.id],
      })
      if (done) toast.success(done)
    },
    onError: handleServerError,
  })
}

const path = (t: Transmittal) => ({ transmittal_id: t.id })

function Documents({ t, editable }: { t: Transmittal; editable: boolean }) {
  const [adding, setAdding] = useState<number[]>([])
  const add = useTransmittalMutation(t, (ids: number[]) =>
    unwrap(
      api.POST('/api/v1/transmittals/{transmittal_id}/documents', {
        params: { path: path(t) },
        body: { file_ids: ids },
      })
    )
  )
  const remove = useTransmittalMutation(t, (id: number) =>
    unwrap(
      api.DELETE(
        '/api/v1/transmittals/{transmittal_id}/documents/{document_id}',
        {
          params: { path: { ...path(t), document_id: id } },
        }
      )
    )
  )
  const latest = useTransmittalMutation(
    t,
    (id: number) =>
      unwrap(
        api.POST(
          '/api/v1/transmittals/{transmittal_id}/documents/{document_id}/latest',
          { params: { path: { ...path(t), document_id: id } } }
        )
      ),
    'Swapped to the latest revision'
  )
  return (
    <div className='grid gap-2'>
      {t.warnings?.length ? (
        <Alert className='border-amber-500/50 text-amber-800 dark:text-amber-300'>
          <AlertTriangle />
          <AlertTitle>Superseded revisions</AlertTitle>
          <AlertDescription>
            {t.warnings.map((w) => (
              <span key={w.document_id} className='flex items-center gap-2'>
                {w.message}
                {editable ? (
                  <Button
                    size='sm'
                    variant='link'
                    className='h-auto p-0'
                    onClick={() => latest.mutate(w.document_id)}
                  >
                    Use rev {w.latest_revision}
                  </Button>
                ) : null}
              </span>
            ))}
          </AlertDescription>
        </Alert>
      ) : null}
      <table className='w-full text-sm'>
        <thead className='text-xs text-muted-foreground'>
          <tr className='border-b text-start'>
            <th className='py-1 text-start'>Document</th>
            <th className='py-1 text-end'>Rev</th>
            <th className='py-1 ps-3 text-start'>Category</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {(t.documents ?? []).map((d) => (
            <tr key={d.id} className='border-b last:border-0'>
              <td className='py-1.5'>
                {d.name}
                {d.is_latest ? null : (
                  <StatusBadge status='superseded' className='ms-2' />
                )}
              </td>
              <td className='py-1.5 text-end'>{d.revision}</td>
              <td className='py-1.5 ps-3'>{label(d.category)}</td>
              <td className='py-1.5 text-end'>
                {editable ? (
                  <button
                    aria-label='Remove document'
                    onClick={() => remove.mutate(d.id)}
                  >
                    <Trash2 className='size-4 text-muted-foreground hover:text-red-600' />
                  </button>
                ) : null}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {editable ? (
        <div className='grid gap-2 rounded-md border p-2'>
          <span className='text-xs font-medium'>Add documents</span>
          <DocumentPicker
            projectId={t.project_id}
            selected={adding}
            onChange={setAdding}
            exclude={(t.documents ?? []).flatMap((d) =>
              d.file_id ? [d.file_id] : []
            )}
          />
          <Button
            size='sm'
            className='w-fit'
            disabled={!adding.length || add.isPending}
            onClick={() =>
              add.mutate(adding, { onSuccess: () => setAdding([]) })
            }
          >
            Add {adding.length || ''}
          </Button>
        </div>
      ) : null}
    </div>
  )
}

function Acknowledge({ t, r }: { t: Transmittal; r: Recipient }) {
  const [note, setNote] = useState(r.acknowledgement_note ?? '')
  const [date, setDate] = useState('')
  const record = useTransmittalMutation(
    t,
    (acknowledged: boolean) =>
      unwrap(
        api.PATCH('/api/v1/transmittals/{transmittal_id}/acknowledge', {
          params: { path: path(t) },
          body: {
            recipient_id: r.id,
            acknowledged,
            note: note || undefined,
            ...(date
              ? acknowledged
                ? { acknowledged_at: new Date(date).toISOString() }
                : { received_at: new Date(date).toISOString() }
              : {}),
          },
        })
      ),
    'Recorded'
  )
  return (
    <div className='grid gap-1.5 ps-4'>
      <div className='flex flex-wrap gap-2'>
        <Input
          type='date'
          className='h-8 w-40'
          aria-label='Date'
          value={date}
          onChange={(e) => setDate(e.target.value)}
        />
        <Input
          className='h-8 flex-1'
          placeholder='Acknowledgement note'
          value={note}
          onChange={(e) => setNote(e.target.value)}
        />
      </div>
      <div className='flex gap-2'>
        {!r.received_at ? (
          <Button
            size='sm'
            variant='outline'
            disabled={record.isPending}
            onClick={() => record.mutate(false)}
          >
            Received
          </Button>
        ) : null}
        <Button
          size='sm'
          variant='outline'
          disabled={record.isPending}
          onClick={() => record.mutate(true)}
        >
          Acknowledged
        </Button>
      </div>
    </div>
  )
}

function Recipients({
  t,
  editable,
  canAcknowledge,
}: {
  t: Transmittal
  editable: boolean
  canAcknowledge: boolean
}) {
  const [adding, setAdding] = useState<number[]>([])
  const add = useTransmittalMutation(t, (ids: number[]) =>
    unwrap(
      api.POST('/api/v1/transmittals/{transmittal_id}/recipients', {
        params: { path: path(t) },
        body: { contact_ids: ids },
      })
    )
  )
  const remove = useTransmittalMutation(t, (id: number) =>
    unwrap(
      api.DELETE(
        '/api/v1/transmittals/{transmittal_id}/recipients/{recipient_id}',
        { params: { path: { ...path(t), recipient_id: id } } }
      )
    )
  )
  const when = (value?: string | null) =>
    value ? new Date(value).toLocaleDateString() : null
  return (
    <div className='grid gap-2'>
      {(t.recipients ?? []).map((r) => (
        <div key={r.id} className='grid gap-1.5 rounded-md border p-2'>
          <div className='flex flex-wrap items-center gap-2 text-sm'>
            <span className='font-medium'>{r.name}</span>
            <span className='text-xs text-muted-foreground'>
              {r.email ?? 'no email'}
            </span>
            <StatusBadge status={r.delivery} className='ms-auto' />
            {editable ? (
              <button
                aria-label='Remove recipient'
                onClick={() => remove.mutate(r.id)}
              >
                <Trash2 className='size-4 text-muted-foreground hover:text-red-600' />
              </button>
            ) : null}
          </div>
          {r.sent_at ? (
            <span className='text-xs text-muted-foreground'>
              Sent {when(r.sent_at)}
              {r.received_at ? ` · received ${when(r.received_at)}` : ''}
              {r.acknowledged_at
                ? ` · acknowledged ${when(r.acknowledged_at)}`
                : ''}
              {r.acknowledgement_note ? ` · “${r.acknowledgement_note}”` : ''}
            </span>
          ) : null}
          {canAcknowledge && !r.acknowledged_at ? (
            <Acknowledge t={t} r={r} />
          ) : null}
        </div>
      ))}
      {editable ? (
        <div className='grid gap-2 rounded-md border p-2'>
          <span className='text-xs font-medium'>Add recipients</span>
          <ContactPicker
            selected={adding}
            onChange={setAdding}
            exclude={(t.recipients ?? []).flatMap((r) =>
              r.contact_id ? [r.contact_id] : []
            )}
          />
          <Button
            size='sm'
            className='w-fit'
            disabled={!adding.length || add.isPending}
            onClick={() =>
              add.mutate(adding, { onSuccess: () => setAdding([]) })
            }
          >
            Add {adding.length || ''}
          </Button>
        </div>
      ) : null}
    </div>
  )
}

function SendButton({ t }: { t: Transmittal }) {
  const [open, setOpen] = useState(false)
  const [message, setMessage] = useState('')
  const send = useTransmittalMutation(
    t,
    () =>
      unwrap(
        api.POST('/api/v1/transmittals/{transmittal_id}/send', {
          params: { path: path(t) },
          body: { message: message || undefined },
        })
      ),
    'Sent'
  )
  const withEmail = (t.recipients ?? []).filter((r) => r.email).length
  return (
    <>
      <Button
        size='sm'
        disabled={!t.document_count || !t.recipient_count}
        onClick={() => setOpen(true)}
      >
        <Send /> Send
      </Button>
      <ConfirmDialog
        open={open}
        onOpenChange={setOpen}
        title={`Send ${t.code}?`}
        isLoading={send.isPending}
        confirmText='Send'
        desc={`${t.document_count} document(s) to ${t.recipient_count} recipient(s); ${withEmail} will be emailed the cover sheet. A sent transmittal can't be changed.`}
        handleConfirm={() =>
          send.mutate(undefined, { onSuccess: () => setOpen(false) })
        }
      >
        {t.warnings?.length ? (
          <p className='text-sm text-amber-700 dark:text-amber-300'>
            {t.warnings.length} document(s) are not the latest revision.
          </p>
        ) : null}
        <Textarea
          rows={3}
          placeholder='Message for the email (optional)'
          value={message}
          onChange={(e) => setMessage(e.target.value)}
        />
      </ConfirmDialog>
    </>
  )
}

function History({ id }: { id: number }) {
  const { data = [] } = useQuery({
    queryKey: ['transmittals', 'history', id],
    queryFn: async () =>
      (await unwrap(
        api.GET('/api/v1/transmittals/{transmittal_id}/history', {
          params: { path: { transmittal_id: id } },
        })
      )) as unknown as HistoryEntry[],
  })
  return (
    <ol className='grid gap-2'>
      {data.map((h, i) => (
        <li key={i} className='flex flex-wrap items-center gap-2 text-sm'>
          <StatusBadge status={h.to_status} />
          <span className='text-muted-foreground'>
            {h.changed_at ? new Date(h.changed_at).toLocaleString() : ''}
            {h.changed_by_name ? ` · ${h.changed_by_name}` : ''}
          </span>
          {h.note ? <span className='italic'>{h.note}</span> : null}
        </li>
      ))}
    </ol>
  )
}

/** One transmittal: documents with revision checks, recipients with delivery status, send and acknowledge. */
export function TransmittalSheet({
  id,
  onClose,
}: {
  id: number
  onClose: () => void
}) {
  const session = useSession()
  const { data: t } = useTransmittal(id)
  const draft = t?.status === 'draft'
  const editable = !!draft && can(session, 'transmittals.update')
  return (
    <RecordSheet
      open
      wide
      onClose={onClose}
      title={t ? `${t.code} · ${t.subject}` : 'Loading…'}
      subtitle={
        t
          ? `${label(t.purpose)}${t.sent_at ? ` · sent ${new Date(t.sent_at).toLocaleDateString()}` : ''}${t.response_due ? ` · response due ${t.response_due}` : ''}`
          : undefined
      }
      badges={t ? <StatusBadge status={t.status} /> : null}
      record={
        t
          ? {
              projectId: t.project_id,
              entityType: 'transmittal',
              entityId: t.id,
            }
          : undefined
      }
      tabs={
        t
          ? {
              Recipients: (
                <Recipients
                  t={t}
                  editable={editable}
                  canAcknowledge={!draft && can(session, 'transmittals.update')}
                />
              ),
              History: <History id={t.id} />,
            }
          : undefined
      }
    >
      {t ? (
        <div className='grid gap-4'>
          <div className='flex flex-wrap gap-2'>
            <Button size='sm' variant='outline' asChild>
              <a href={coverUrl(t.id)} target='_blank' rel='noreferrer'>
                <FileText /> Cover sheet
              </a>
            </Button>
            {draft && can(session, 'transmittals.submit') ? (
              <SendButton t={t} />
            ) : null}
          </div>
          {t.notes ? (
            <p className='rounded-md border p-3 text-sm whitespace-pre-wrap'>
              {t.notes}
            </p>
          ) : null}
          <Documents t={t} editable={editable} />
        </div>
      ) : null}
    </RecordSheet>
  )
}
