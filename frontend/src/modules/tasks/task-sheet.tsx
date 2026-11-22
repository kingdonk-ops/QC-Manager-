import { useState } from 'react'
import { useRouter } from '@tanstack/react-router'
import { ExternalLink, Trash2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { can, useSession } from '@/lib/session'
import { Button } from '@/components/ui/button'
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
import { RecordSheet } from '@/components/records/record-sheet'
import { statusLabel } from '@/components/records/status'
import { StatusBadge } from '@/components/records/status-badge'
import {
  type Task,
  type TaskCreate,
  useCreateTask,
  useDeleteTask,
  useUpdateTask,
} from './api'
import { AssigneeSelect } from './assignee-select'
import { PRIORITIES, STATUSES, TYPES, sourceLink } from './constants'

type Draft = {
  title: string
  description: string
  type: string
  status: string
  priority: string
  assignee_id: number | null
  start_date: string
  due_date: string
  type_fields: Record<string, string>
}

const blank: Draft = {
  title: '',
  description: '',
  type: 'general',
  status: 'todo',
  priority: 'medium',
  assignee_id: null,
  start_date: '',
  due_date: '',
  type_fields: {},
}

function fromTask(task: Task): Draft {
  return {
    title: task.title,
    description: task.description ?? '',
    type: task.type,
    status: task.status,
    priority: task.priority,
    assignee_id: task.assignee_id ?? null,
    start_date: task.start_date ?? '',
    due_date: task.due_date ?? '',
    type_fields: Object.fromEntries(
      Object.entries(task.type_fields ?? {}).map(([k, v]) => [k, String(v)])
    ),
  }
}

function Pick({
  id,
  label,
  value,
  options,
  onChange,
  disabled,
}: {
  id: string
  label: string
  value: string
  options: readonly string[]
  onChange: (v: string) => void
  disabled?: boolean
}) {
  return (
    <div className='grid gap-1.5'>
      <Label htmlFor={id}>{label}</Label>
      <Select value={value} onValueChange={onChange} disabled={disabled}>
        <SelectTrigger id={id} className='w-full'>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {options.map((o) => (
            <SelectItem key={o} value={o}>
              {statusLabel(o)}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  )
}

/** One task's details, or a new task when ``task`` is null. */
export function TaskSheet({
  open,
  task,
  projectId,
  typeFields,
  onClose,
}: {
  open: boolean
  task: Task | null
  projectId: number
  typeFields: Record<string, string[]>
  onClose: () => void
}) {
  const { t } = useTranslation()
  const session = useSession()
  const router = useRouter()
  const editable = can(session, task ? 'tasks.update' : 'tasks.create')
  const create = useCreateTask(projectId)
  const update = useUpdateTask(projectId)
  const remove = useDeleteTask(projectId)
  const [draft, setDraft] = useState<Draft>(task ? fromTask(task) : blank)
  const set = (patch: Partial<Draft>) => setDraft((d) => ({ ...d, ...patch }))
  const extra = typeFields[draft.type] ?? []
  const link = task ? sourceLink(task) : null

  const save = () => {
    const body = {
      title: draft.title.trim(),
      description: draft.description || null,
      type: draft.type,
      status: draft.status,
      priority: draft.priority,
      assignee_id: draft.assignee_id,
      start_date: draft.start_date || null,
      due_date: draft.due_date || null,
      type_fields: Object.fromEntries(
        extra
          .filter((k) => draft.type_fields[k])
          .map((k) => [k, draft.type_fields[k]])
      ),
    } as Omit<TaskCreate, 'project_id'>
    if (task)
      update.mutate(
        { id: task.id, body },
        {
          onSuccess: () => {
            toast.success(t('tasks.saved'))
            onClose()
          },
        }
      )
    else
      create.mutate(
        { ...body, project_id: projectId },
        {
          onSuccess: (created) => {
            toast.success(t('tasks.created', { code: created.code }))
            onClose()
          },
        }
      )
  }

  return (
    <RecordSheet
      open={open}
      onClose={onClose}
      title={task ? `${task.code} ${task.title}` : t('tasks.new')}
      badges={
        task ? (
          <>
            <StatusBadge status={task.status} />
            <StatusBadge status={task.priority} />
            {task.overdue ? <StatusBadge status='overdue' /> : null}
          </>
        ) : null
      }
      record={
        task ? { projectId, entityType: 'task', entityId: task.id } : undefined
      }
    >
      <form
        className='grid gap-3'
        onSubmit={(e) => {
          e.preventDefault()
          save()
        }}
      >
        {link ? (
          <button
            type='button'
            className='flex w-fit items-center gap-1 text-sm text-primary underline-offset-4 hover:underline'
            onClick={() => router.history.push(link)}
          >
            <ExternalLink className='size-3.5' />
            {t('tasks.source', {
              type: statusLabel(task?.entity_type ?? ''),
            })}
          </button>
        ) : null}
        <div className='grid gap-1.5'>
          <Label htmlFor='task-title'>{t('tasks.title_field')}</Label>
          <Input
            id='task-title'
            value={draft.title}
            onChange={(e) => set({ title: e.target.value })}
            required
            maxLength={300}
            disabled={!editable}
          />
        </div>
        <div className='grid gap-1.5'>
          <Label htmlFor='task-description'>{t('tasks.description')}</Label>
          <Textarea
            id='task-description'
            rows={4}
            value={draft.description}
            onChange={(e) => set({ description: e.target.value })}
            disabled={!editable}
          />
        </div>
        <div className='grid grid-cols-2 gap-3'>
          <Pick
            id='task-type'
            label={t('tasks.type')}
            value={draft.type}
            options={TYPES}
            onChange={(type) => set({ type })}
            disabled={!editable}
          />
          <Pick
            id='task-status'
            label={t('tasks.status_field')}
            value={draft.status}
            options={STATUSES}
            onChange={(status) => set({ status })}
            disabled={!editable}
          />
          <Pick
            id='task-priority'
            label={t('tasks.priority')}
            value={draft.priority}
            options={PRIORITIES}
            onChange={(priority) => set({ priority })}
            disabled={!editable}
          />
          <div className='grid gap-1.5'>
            <Label htmlFor='task-assignee'>{t('tasks.assignee')}</Label>
            <AssigneeSelect
              id='task-assignee'
              value={draft.assignee_id}
              onChange={(assignee_id) => set({ assignee_id })}
              disabled={!editable}
            />
          </div>
          <div className='grid gap-1.5'>
            <Label htmlFor='task-start'>{t('tasks.start')}</Label>
            <Input
              id='task-start'
              type='date'
              value={draft.start_date}
              onChange={(e) => set({ start_date: e.target.value })}
              disabled={!editable}
            />
          </div>
          <div className='grid gap-1.5'>
            <Label htmlFor='task-due'>{t('tasks.due')}</Label>
            <Input
              id='task-due'
              type='date'
              value={draft.due_date}
              onChange={(e) => set({ due_date: e.target.value })}
              disabled={!editable}
            />
          </div>
          {extra.map((field) => (
            <div key={field} className='grid gap-1.5'>
              <Label htmlFor={`task-tf-${field}`}>{statusLabel(field)}</Label>
              <Input
                id={`task-tf-${field}`}
                value={draft.type_fields[field] ?? ''}
                onChange={(e) =>
                  set({
                    type_fields: {
                      ...draft.type_fields,
                      [field]: e.target.value,
                    },
                  })
                }
                disabled={!editable}
              />
            </div>
          ))}
        </div>
        {editable ? (
          <div className='flex items-center gap-2 pt-2'>
            <Button
              type='submit'
              disabled={create.isPending || update.isPending}
            >
              {task ? t('common.save') : t('common.create')}
            </Button>
            {task && can(session, 'tasks.delete') ? (
              <Button
                type='button'
                variant='ghost'
                className='ms-auto text-red-600'
                onClick={() => {
                  if (window.confirm(t('tasks.confirm_delete')))
                    remove.mutate(task.id, { onSuccess: onClose })
                }}
              >
                <Trash2 /> {t('tasks.delete')}
              </Button>
            ) : null}
          </div>
        ) : null}
      </form>
    </RecordSheet>
  )
}
