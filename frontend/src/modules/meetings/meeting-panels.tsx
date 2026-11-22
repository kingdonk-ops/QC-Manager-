import { useState } from 'react'
import { useRouter } from '@tanstack/react-router'
import { AssigneeSelect } from '@/modules/tasks/assignee-select'
import { ListPlus, Plus, Trash2, X } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { can, useSession } from '@/lib/session'
import { cn } from '@/lib/utils'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { statusLabel } from '@/components/records/status'
import { StatusBadge } from '@/components/records/status-badge'
import {
  type Action,
  type ActionUpdate,
  type MeetingDetail,
  useActions,
  useAgenda,
  useAttendees,
  useHistory,
  usePrevious,
  useUpdateMeeting,
} from './api'
import { formatWhen } from './format'
import { PersonPicker } from './person-picker'

const ACTION_STATUSES = ['open', 'done', 'cancelled'] as const

export function AttendeesPanel({
  meeting,
  editable,
}: {
  meeting: MeetingDetail
  editable: boolean
}) {
  const { t } = useTranslation()
  const attendees = useAttendees(meeting.id)
  const list = meeting.attendees ?? []
  const chosen = new Set(
    list.map((a) => (a.user_id ? `u:${a.user_id}` : `c:${a.contact_id}`))
  )
  const present = list.filter((a) => a.attended).length
  return (
    <div className='grid gap-2'>
      <div className='flex items-center justify-between'>
        <span className='text-sm text-muted-foreground'>
          {t('meetings.present_of', { present, invited: list.length })}
        </span>
        {editable ? (
          <PersonPicker
            projectId={meeting.project_id}
            exclude={chosen}
            label={t('meetings.invite')}
            onPick={(person) => attendees.add.mutate(person)}
          />
        ) : null}
      </div>
      {list.length ? (
        <ul className='grid gap-1'>
          {list.map((a) => (
            <li
              key={a.id}
              className='flex items-center gap-3 rounded-md border px-3 py-2 text-sm'
            >
              <Checkbox
                checked={a.attended}
                disabled={!editable}
                aria-label={t('meetings.attended')}
                onCheckedChange={(v) =>
                  attendees.update.mutate({
                    attendeeId: a.id,
                    attended: v === true,
                  })
                }
              />
              <span className='grid flex-1'>
                <span className='font-medium'>{a.name}</span>
                <span className='text-xs text-muted-foreground'>
                  {a.email ?? t('meetings.no_email')}
                </span>
              </span>
              <Badge variant='outline'>
                {a.user_id ? t('meetings.user') : t('meetings.contact')}
              </Badge>
              {editable ? (
                <button
                  type='button'
                  className='text-muted-foreground hover:text-red-600'
                  aria-label={t('meetings.remove')}
                  onClick={() => attendees.remove.mutate(a.id)}
                >
                  <X className='size-4' />
                </button>
              ) : null}
            </li>
          ))}
        </ul>
      ) : (
        <p className='text-sm text-muted-foreground'>
          {t('meetings.no_attendees')}
        </p>
      )}
    </div>
  )
}

function SavedText({
  id,
  label,
  value,
  onSave,
  disabled,
  rows = 3,
}: {
  id: string
  label: string
  value: string | null | undefined
  onSave: (v: string | null) => void
  disabled?: boolean
  rows?: number
}) {
  const [text, setText] = useState(value ?? '')
  return (
    <div className='grid gap-1'>
      <Label htmlFor={id} className='text-xs text-muted-foreground'>
        {label}
      </Label>
      <Textarea
        id={id}
        rows={rows}
        value={text}
        disabled={disabled}
        onChange={(e) => setText(e.target.value)}
        onBlur={() => text !== (value ?? '') && onSave(text || null)}
      />
    </div>
  )
}

export function MinutesPanel({
  meeting,
  editable,
}: {
  meeting: MeetingDetail
  editable: boolean
}) {
  const { t } = useTranslation()
  const update = useUpdateMeeting(meeting.id)
  const agenda = useAgenda(meeting.id)
  return (
    <div className='grid gap-4'>
      <SavedText
        id='minutes-summary'
        label={t('meetings.summary')}
        value={meeting.minutes}
        disabled={!editable}
        rows={4}
        onSave={(minutes) => update.mutate({ minutes })}
      />
      {(meeting.agenda ?? []).map((item) => (
        <section key={item.id} className='grid gap-2 rounded-md border p-3'>
          <h4 className='text-sm font-medium'>
            {item.number}. {item.title}
            {item.presenter_name ? (
              <span className='font-normal text-muted-foreground'>
                {' '}
                · {item.presenter_name}
              </span>
            ) : null}
          </h4>
          <SavedText
            id={`notes-${item.id}`}
            label={t('meetings.discussion')}
            value={item.notes}
            disabled={!editable}
            onSave={(notes) =>
              agenda.update.mutate({ itemId: item.id, body: { notes } })
            }
          />
          <SavedText
            id={`decisions-${item.id}`}
            label={t('meetings.decisions')}
            value={item.decisions}
            disabled={!editable}
            rows={2}
            onSave={(decisions) =>
              agenda.update.mutate({ itemId: item.id, body: { decisions } })
            }
          />
        </section>
      ))}
    </div>
  )
}

function ActionRow({
  action,
  editable,
  canTask,
  onUpdate,
  onRemove,
  onTask,
  projectId,
}: {
  projectId: number
  action: Action
  editable: boolean
  canTask: boolean
  onUpdate: (body: ActionUpdate) => void
  onRemove: () => void
  onTask: () => void
}) {
  const { t } = useTranslation()
  const router = useRouter()
  const [description, setDescription] = useState(action.description)
  return (
    <tr className='border-t align-top'>
      <td className='p-1.5'>
        <Textarea
          rows={1}
          className='min-h-8'
          value={description}
          disabled={!editable}
          aria-label={t('meetings.action')}
          onChange={(e) => setDescription(e.target.value)}
          onBlur={() =>
            description.trim() &&
            description !== action.description &&
            onUpdate({ description })
          }
        />
      </td>
      <td className='w-44 p-1.5'>
        <AssigneeSelect
          className='h-8 w-full'
          value={action.assignee_id}
          disabled={!editable}
          onChange={(assignee_id) => onUpdate({ assignee_id })}
        />
      </td>
      <td className='w-36 p-1.5'>
        <Input
          type='date'
          className={cn(
            'h-8',
            action.overdue && 'text-red-600 dark:text-red-400'
          )}
          value={action.due_date ?? ''}
          disabled={!editable}
          aria-label={t('meetings.due')}
          onChange={(e) => onUpdate({ due_date: e.target.value || null })}
        />
      </td>
      <td className='w-32 p-1.5'>
        <Select
          value={action.status}
          disabled={!editable}
          onValueChange={(status) =>
            onUpdate({ status: status as ActionUpdate['status'] })
          }
        >
          <SelectTrigger size='sm' className='w-full'>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {ACTION_STATUSES.map((s) => (
              <SelectItem key={s} value={s}>
                {statusLabel(s)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </td>
      <td className='w-40 p-1.5'>
        {action.task_id ? (
          <button
            type='button'
            className='flex items-center gap-1 text-sm text-primary hover:underline'
            onClick={() =>
              router.history.push(
                `/tasks?project=${projectId}&task=${action.task_id}`
              )
            }
          >
            <span className='font-mono'>{action.task_code}</span>
            <StatusBadge status={action.task_status} />
          </button>
        ) : canTask ? (
          <Button size='sm' variant='outline' onClick={onTask}>
            <ListPlus /> {t('meetings.to_task')}
          </Button>
        ) : null}
      </td>
      <td className='w-8 p-1.5'>
        {editable ? (
          <button
            type='button'
            className='mt-1.5 text-muted-foreground hover:text-red-600'
            aria-label={t('meetings.remove')}
            onClick={onRemove}
          >
            <Trash2 className='size-4' />
          </button>
        ) : null}
      </td>
    </tr>
  )
}

export function ActionsPanel({
  meeting,
  editable,
}: {
  meeting: MeetingDetail
  editable: boolean
}) {
  const { t } = useTranslation()
  const session = useSession()
  const actions = useActions(meeting.id)
  const canTask = editable && can(session, 'tasks.create')
  const [draft, setDraft] = useState({
    description: '',
    assignee_id: null as number | null,
    due_date: '',
  })
  const list = meeting.actions ?? []
  return (
    <div className='grid gap-3'>
      <div className='overflow-x-auto rounded-md border'>
        <table className='w-full text-sm'>
          <thead className='bg-muted/50 text-xs text-muted-foreground'>
            <tr>
              <th className='p-1.5 text-start font-medium'>
                {t('meetings.action')}
              </th>
              <th className='p-1.5 text-start font-medium'>
                {t('meetings.owner')}
              </th>
              <th className='p-1.5 text-start font-medium'>
                {t('meetings.due')}
              </th>
              <th className='p-1.5 text-start font-medium'>
                {t('meetings.status')}
              </th>
              <th className='p-1.5 text-start font-medium'>
                {t('meetings.task')}
              </th>
              <th />
            </tr>
          </thead>
          <tbody>
            {list.map((a) => (
              <ActionRow
                key={`${a.id}-${a.description}`}
                action={a}
                projectId={meeting.project_id}
                editable={editable}
                canTask={canTask}
                onUpdate={(body) =>
                  actions.update.mutate({ actionId: a.id, body })
                }
                onRemove={() => actions.remove.mutate(a.id)}
                onTask={() =>
                  actions.toTask.mutate(a.id, {
                    onSuccess: (r) =>
                      toast.success(
                        t('meetings.task_created', { code: r.task_code })
                      ),
                  })
                }
              />
            ))}
            {!list.length ? (
              <tr>
                <td
                  colSpan={6}
                  className='p-3 text-center text-muted-foreground'
                >
                  {t('meetings.no_actions')}
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
      {editable ? (
        <form
          className='flex flex-wrap items-center gap-2'
          onSubmit={(e) => {
            e.preventDefault()
            if (!draft.description.trim()) return
            actions.add.mutate(
              {
                description: draft.description.trim(),
                assignee_id: draft.assignee_id,
                due_date: draft.due_date || null,
                status: 'open',
              },
              {
                onSuccess: () =>
                  setDraft({
                    description: '',
                    assignee_id: null,
                    due_date: '',
                  }),
              }
            )
          }}
        >
          <Input
            className='h-8 min-w-56 flex-1'
            placeholder={t('meetings.new_action')}
            value={draft.description}
            onChange={(e) =>
              setDraft({ ...draft, description: e.target.value })
            }
          />
          <AssigneeSelect
            className='h-8 w-44'
            value={draft.assignee_id}
            onChange={(assignee_id) => setDraft({ ...draft, assignee_id })}
          />
          <Input
            type='date'
            className='h-8 w-36'
            aria-label={t('meetings.due')}
            value={draft.due_date}
            onChange={(e) => setDraft({ ...draft, due_date: e.target.value })}
          />
          <Button size='sm' type='submit' disabled={actions.add.isPending}>
            <Plus /> {t('meetings.add')}
          </Button>
        </form>
      ) : null}
    </div>
  )
}

export function PreviousPanel({
  meeting,
  editable,
}: {
  meeting: MeetingDetail
  editable: boolean
}) {
  const { t } = useTranslation()
  const { data } = usePrevious(meeting.id, Boolean(meeting.series_id))
  const actions = useActions(meeting.id)
  if (!meeting.series_id)
    return (
      <p className='text-sm text-muted-foreground'>
        {t('meetings.not_in_series')}
      </p>
    )
  if (!data?.meeting)
    return (
      <p className='text-sm text-muted-foreground'>
        {t('meetings.first_in_series')}
      </p>
    )
  const prev = data.meeting
  return (
    <div className='grid gap-4'>
      <div className='grid gap-1'>
        <h4 className='text-sm font-medium'>
          {prev.code} · {formatWhen(prev.starts_at)}{' '}
          <StatusBadge status={prev.status} />
        </h4>
        {prev.minutes ? (
          <p className='text-sm whitespace-pre-wrap'>{prev.minutes}</p>
        ) : null}
      </div>
      {data.agenda?.some((i) => i.decisions || i.notes) ? (
        <section className='grid gap-1'>
          <h4 className='text-sm font-medium'>{t('meetings.decisions')}</h4>
          <ul className='grid gap-1 text-sm'>
            {data.agenda
              .filter((i) => i.decisions || i.notes)
              .map((i) => (
                <li key={i.id} className='rounded-md border p-2'>
                  <span className='font-medium'>
                    {i.number}. {i.title}
                  </span>
                  {i.notes ? (
                    <p className='whitespace-pre-wrap text-muted-foreground'>
                      {i.notes}
                    </p>
                  ) : null}
                  {i.decisions ? (
                    <p className='whitespace-pre-wrap'>{i.decisions}</p>
                  ) : null}
                </li>
              ))}
          </ul>
        </section>
      ) : null}
      <section className='grid gap-1'>
        <h4 className='text-sm font-medium'>
          {t('meetings.open_actions', {
            count: data.open_actions?.length ?? 0,
          })}
        </h4>
        <ul className='grid gap-1 text-sm'>
          {(data.open_actions ?? []).map((a) => (
            <li
              key={a.id}
              className='flex items-center gap-2 rounded-md border p-2'
            >
              <span className='font-mono text-xs text-muted-foreground'>
                {a.meeting_code}
              </span>
              <span className='flex-1'>{a.description}</span>
              {a.assignee_name ? (
                <span className='text-xs'>{a.assignee_name}</span>
              ) : null}
              {a.due_date ? (
                <span
                  className={cn(
                    'text-xs',
                    a.overdue && 'text-red-600 dark:text-red-400'
                  )}
                >
                  {a.due_date}
                </span>
              ) : null}
              {editable ? (
                <Button
                  size='sm'
                  variant='ghost'
                  onClick={() =>
                    actions.update.mutate({
                      actionId: a.id,
                      meetingId: a.meeting_id,
                      body: { status: 'done' },
                    })
                  }
                >
                  {t('meetings.mark_done')}
                </Button>
              ) : null}
            </li>
          ))}
        </ul>
      </section>
    </div>
  )
}

export function HistoryPanel({ meetingId }: { meetingId: number }) {
  const { data = [] } = useHistory(meetingId)
  return (
    <ul className='grid gap-1 text-sm'>
      {data.map((h, i) => (
        <li key={i} className='flex items-center gap-2'>
          <span className='w-40 text-xs text-muted-foreground'>
            {h.changed_at ? formatWhen(String(h.changed_at)) : ''}
          </span>
          <StatusBadge status={String(h.to_status)} />
          {h.note ? (
            <span className='text-muted-foreground'>{String(h.note)}</span>
          ) : null}
        </li>
      ))}
    </ul>
  )
}
