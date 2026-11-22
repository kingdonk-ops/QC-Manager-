import { useState } from 'react'
import { ArrowDown, ArrowUp, GripVertical, Plus, Trash2, X } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  type AgendaItem,
  type AgendaItemUpdate,
  type MeetingDetail,
  useAgenda,
} from './api'
import { reorder } from './format'
import { PersonPicker } from './person-picker'

function Row({
  item,
  editable,
  onSave,
  onRemove,
  onMove,
  first,
  last,
  projectId,
  dragProps,
}: {
  item: AgendaItem
  editable: boolean
  onSave: (body: AgendaItemUpdate) => void
  onRemove: () => void
  onMove: (delta: -1 | 1) => void
  first: boolean
  last: boolean
  projectId: number
  dragProps: React.HTMLAttributes<HTMLDivElement> & { draggable?: boolean }
}) {
  const { t } = useTranslation()
  const [title, setTitle] = useState(item.title)
  const [minutes, setMinutes] = useState(
    item.duration_minutes == null ? '' : String(item.duration_minutes)
  )
  return (
    <div
      {...dragProps}
      className='flex flex-wrap items-center gap-2 rounded-md border bg-card p-2'
    >
      {editable ? (
        <GripVertical className='size-4 cursor-grab text-muted-foreground' />
      ) : null}
      <span className='w-6 text-end text-sm font-semibold tabular-nums'>
        {item.number}.
      </span>
      <Input
        className='h-8 min-w-40 flex-1'
        value={title}
        disabled={!editable}
        aria-label={t('meetings.item_title')}
        onChange={(e) => setTitle(e.target.value)}
        onBlur={() => title.trim() && title !== item.title && onSave({ title })}
      />
      <Input
        className='h-8 w-20'
        type='number'
        min={0}
        max={1440}
        placeholder={t('meetings.min')}
        aria-label={t('meetings.minutes_allocated')}
        value={minutes}
        disabled={!editable}
        onChange={(e) => setMinutes(e.target.value)}
        onBlur={() => {
          const value = minutes === '' ? null : Number(minutes)
          if (value !== (item.duration_minutes ?? null))
            onSave({ duration_minutes: value })
        }}
      />
      {item.presenter_name ? (
        <span className='flex items-center gap-1 rounded bg-muted px-2 py-1 text-xs'>
          {item.presenter_name}
          {editable ? (
            <button
              type='button'
              aria-label={t('meetings.clear_presenter')}
              onClick={() =>
                onSave({ presenter_user_id: null, presenter_contact_id: null })
              }
            >
              <X className='size-3' />
            </button>
          ) : null}
        </span>
      ) : editable ? (
        <PersonPicker
          projectId={projectId}
          label={t('meetings.presenter')}
          onPick={(p) =>
            onSave({
              presenter_user_id: p.user_id ?? null,
              presenter_contact_id: p.contact_id ?? null,
            })
          }
        />
      ) : null}
      {editable ? (
        <span className='flex items-center'>
          <Button
            size='icon'
            variant='ghost'
            className='size-7'
            disabled={first}
            aria-label={t('meetings.move_up')}
            onClick={() => onMove(-1)}
          >
            <ArrowUp />
          </Button>
          <Button
            size='icon'
            variant='ghost'
            className='size-7'
            disabled={last}
            aria-label={t('meetings.move_down')}
            onClick={() => onMove(1)}
          >
            <ArrowDown />
          </Button>
          <Button
            size='icon'
            variant='ghost'
            className='size-7 text-muted-foreground hover:text-red-600'
            aria-label={t('meetings.remove')}
            onClick={onRemove}
          >
            <Trash2 />
          </Button>
        </span>
      ) : null}
    </div>
  )
}

export function AgendaBuilder({
  meeting,
  editable,
}: {
  meeting: MeetingDetail
  editable: boolean
}) {
  const { t } = useTranslation()
  const agenda = useAgenda(meeting.id)
  const items = meeting.agenda ?? []
  const ids = items.map((i) => i.id)
  const [draft, setDraft] = useState({ title: '', minutes: '' })
  const [dragId, setDragId] = useState<number | null>(null)
  const [overId, setOverId] = useState<number | null>(null)
  const total = items.reduce((n, i) => n + (i.duration_minutes ?? 0), 0)

  const move = (id: number, delta: -1 | 1) => {
    const at = ids.indexOf(id)
    const next = [...ids]
    next.splice(at, 1)
    next.splice(at + delta, 0, id)
    agenda.reorder.mutate(next)
  }

  return (
    <div className='grid gap-2'>
      <div className='flex items-center justify-between text-sm text-muted-foreground'>
        <span>{t('meetings.items', { count: items.length })}</span>
        <span>
          {t('meetings.total_time', {
            total,
            planned: meeting.duration_minutes,
          })}
        </span>
      </div>
      {items.map((item, index) => (
        <div
          key={item.id}
          className={cn(
            overId === item.id &&
              dragId !== item.id &&
              'border-t-2 border-primary'
          )}
        >
          <Row
            key={`${item.id}-${item.title}-${item.duration_minutes}`}
            item={item}
            editable={editable}
            projectId={meeting.project_id}
            first={index === 0}
            last={index === items.length - 1}
            onSave={(body) => agenda.update.mutate({ itemId: item.id, body })}
            onRemove={() => agenda.remove.mutate(item.id)}
            onMove={(delta) => move(item.id, delta)}
            dragProps={
              editable
                ? {
                    draggable: true,
                    onDragStart: (e) => {
                      e.dataTransfer.effectAllowed = 'move'
                      setDragId(item.id)
                    },
                    onDragEnd: () => {
                      setDragId(null)
                      setOverId(null)
                    },
                    onDragOver: (e) => {
                      if (dragId === null) return
                      e.preventDefault()
                      setOverId(item.id)
                    },
                    onDrop: (e) => {
                      e.preventDefault()
                      if (dragId !== null && dragId !== item.id)
                        agenda.reorder.mutate(reorder(ids, dragId, item.id))
                      setDragId(null)
                      setOverId(null)
                    },
                  }
                : {}
            }
          />
        </div>
      ))}
      {!items.length ? (
        <p className='text-sm text-muted-foreground'>
          {t('meetings.no_agenda')}
        </p>
      ) : null}
      {editable ? (
        <form
          className='flex items-center gap-2'
          onSubmit={(e) => {
            e.preventDefault()
            if (!draft.title.trim()) return
            agenda.add.mutate(
              {
                title: draft.title.trim(),
                duration_minutes: draft.minutes ? Number(draft.minutes) : null,
              },
              { onSuccess: () => setDraft({ title: '', minutes: '' }) }
            )
          }}
        >
          <Input
            className='h-8 flex-1'
            placeholder={t('meetings.new_item')}
            value={draft.title}
            maxLength={300}
            onChange={(e) => setDraft({ ...draft, title: e.target.value })}
          />
          <Input
            className='h-8 w-20'
            type='number'
            min={0}
            max={1440}
            placeholder={t('meetings.min')}
            value={draft.minutes}
            onChange={(e) => setDraft({ ...draft, minutes: e.target.value })}
          />
          <Button size='sm' type='submit' disabled={agenda.add.isPending}>
            <Plus /> {t('meetings.add')}
          </Button>
        </form>
      ) : null}
    </div>
  )
}
