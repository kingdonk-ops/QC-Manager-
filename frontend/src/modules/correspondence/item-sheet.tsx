import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowDownLeft, ArrowUpRight, Reply } from 'lucide-react'
import { toast } from 'sonner'
import { api, unwrap } from '@/api/client'
import { handleServerError } from '@/lib/handle-server-error'
import { can, useSession } from '@/lib/session'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { RecordSheet } from '@/components/records/record-sheet'
import { StatusBadge } from '@/components/records/status-badge'
import { NEXT, corKeys, label, typeName, useHistory, type Item } from './api'

export function DirectionIcon({ direction }: { direction: string }) {
  return direction === 'incoming' ? (
    <ArrowDownLeft
      className='size-4 text-blue-600'
      aria-label='Incoming'
      role='img'
    />
  ) : (
    <ArrowUpRight
      className='size-4 text-green-600'
      aria-label='Outgoing'
      role='img'
    />
  )
}

function Field({ name, value }: { name: string; value: React.ReactNode }) {
  return (
    <div className='grid gap-0.5'>
      <span className='text-xs text-muted-foreground'>{name}</span>
      <span className='text-sm'>{value || '—'}</span>
    </div>
  )
}

function Details({ item, onReply }: { item: Item; onReply: () => void }) {
  const session = useSession()
  const queryClient = useQueryClient()
  const move = useMutation({
    mutationFn: (status: string) =>
      unwrap(
        api.PATCH('/api/v1/correspondence/{item_id}', {
          params: { path: { item_id: item.id } },
          body: { status: status as never },
        })
      ),
    onSuccess: (data) => {
      queryClient.setQueryData(corKeys.one(item.id), data)
      void queryClient.invalidateQueries({ queryKey: ['correspondence'] })
      toast.success('Updated')
    },
    onError: handleServerError,
  })
  return (
    <div className='grid gap-4'>
      <div className='grid grid-cols-2 gap-3'>
        <Field
          name='Direction'
          value={
            <span className='flex items-center gap-1'>
              <DirectionIcon direction={item.direction} />
              {label(item.direction)}
            </span>
          }
        />
        <Field name='Type' value={typeName(item)} />
        <Field name='From' value={item.sender_name} />
        <Field
          name='To'
          value={(item.recipients ?? []).map((r) => r.name).join(', ')}
        />
        <Field name='Sent' value={item.date_sent} />
        <Field name='Received' value={item.date_received} />
        <Field
          name='Response required by'
          value={
            item.response_required_by ? (
              <span className={cn(item.overdue && 'font-medium text-red-600')}>
                {item.response_required_by}
                {item.overdue ? ' (overdue)' : ''}
              </span>
            ) : null
          }
        />
        <Field name='Their reference' value={item.external_reference} />
        <Field name='In reply to' value={item.in_reply_to_reference} />
      </div>
      {item.body ? (
        <div className='grid gap-1'>
          <span className='text-xs text-muted-foreground'>Body</span>
          <p className='rounded-md border p-3 text-sm whitespace-pre-wrap'>
            {item.body}
          </p>
        </div>
      ) : null}
      <div className='flex flex-wrap items-center gap-2'>
        {can(session, 'correspondence.update')
          ? (NEXT[item.status] ?? []).map((s) => (
              <Button
                key={s}
                size='sm'
                variant='outline'
                disabled={move.isPending}
                onClick={() => move.mutate(s)}
              >
                Mark {label(s).toLowerCase()}
              </Button>
            ))
          : null}
        {can(session, 'correspondence.create') ? (
          <Button size='sm' className='ms-auto' onClick={onReply}>
            <Reply /> Reply
          </Button>
        ) : null}
      </div>
    </div>
  )
}

function Thread({ id, onOpen }: { id: number; onOpen: (id: number) => void }) {
  const { data = [] } = useQuery({
    queryKey: corKeys.thread(id),
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/correspondence/{item_id}/thread', {
          params: { path: { item_id: id } },
        })
      ),
  })
  return (
    <div className='grid gap-2'>
      {data.map((entry) => (
        <button
          key={entry.id}
          onClick={() => onOpen(entry.id)}
          style={{
            marginInlineStart: `${Math.min(entry.depth ?? 0, 6) * 16}px`,
          }}
          className={cn(
            'grid gap-1 rounded-md border p-3 text-start hover:bg-muted/50',
            entry.id === id && 'border-primary'
          )}
        >
          <div className='flex items-center gap-2 text-xs text-muted-foreground'>
            <DirectionIcon direction={entry.direction} />
            <span className='font-medium text-foreground'>
              {entry.reference}
            </span>
            {entry.date_sent ?? entry.date_received ?? ''}
            <span>· {entry.sender_name ?? 'Us'}</span>
            <StatusBadge status={entry.status} className='ms-auto' />
          </div>
          <span className='text-sm font-medium'>{entry.subject}</span>
          {entry.body ? (
            <span className='line-clamp-2 text-xs text-muted-foreground'>
              {entry.body}
            </span>
          ) : null}
        </button>
      ))}
    </div>
  )
}

function History({ id }: { id: number }) {
  const { data = [] } = useHistory(id)
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

/** One item: details and status, the whole thread, history, comments and attachments. */
export function ItemSheet({
  id,
  onClose,
  onOpen,
  onReply,
}: {
  id: number
  onClose: () => void
  onOpen: (id: number) => void
  onReply: (item: Item) => void
}) {
  const { data: item } = useQuery({
    queryKey: corKeys.one(id),
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/correspondence/{item_id}', {
          params: { path: { item_id: id } },
        })
      ),
  })
  return (
    <RecordSheet
      open
      wide
      onClose={onClose}
      title={item ? `${item.reference} · ${item.subject}` : 'Loading…'}
      badges={
        item ? (
          <>
            <StatusBadge status={item.status} />
            {item.overdue ? <StatusBadge status='overdue' /> : null}
          </>
        ) : null
      }
      record={
        item
          ? {
              projectId: item.project_id,
              entityType: 'correspondence',
              entityId: item.id,
            }
          : undefined
      }
      tabs={
        item
          ? {
              Thread: <Thread id={item.id} onOpen={onOpen} />,
              History: <History id={item.id} />,
            }
          : undefined
      }
    >
      {item ? <Details item={item} onReply={() => onReply(item)} /> : null}
    </RecordSheet>
  )
}
