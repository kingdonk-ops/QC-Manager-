import type { Task, TaskStatus } from './api'

export const STATUSES: TaskStatus[] = ['todo', 'in_progress', 'review', 'done']

export const TYPES = [
  'general',
  'design',
  'procurement',
  'construction',
  'commissioning',
] as const

export const PRIORITIES = ['critical', 'high', 'medium', 'low'] as const

/** A colour per task type, for the card's edge and the calendar chip. */
export const TYPE_COLOURS: Record<string, string> = {
  general: 'bg-slate-400',
  design: 'bg-violet-500',
  procurement: 'bg-amber-500',
  construction: 'bg-sky-500',
  commissioning: 'bg-emerald-500',
}

export const PRIORITY_TEXT: Record<string, string> = {
  critical: 'text-red-600 dark:text-red-400',
  high: 'text-amber-600 dark:text-amber-400',
  medium: 'text-muted-foreground',
  low: 'text-muted-foreground/70',
}

export type Filters = {
  mine: boolean
  type: string
  priority: string
  search: string
  overdue: boolean
}

export const NO_FILTERS: Filters = {
  mine: false,
  type: 'all',
  priority: 'all',
  search: '',
  overdue: false,
}

export function matches(task: Task, f: Filters, me: number) {
  if (f.mine && task.assignee_id !== me) return false
  if (f.type !== 'all' && task.type !== f.type) return false
  if (f.priority !== 'all' && task.priority !== f.priority) return false
  if (f.overdue && !task.overdue) return false
  if (f.search) {
    const q = f.search.toLowerCase()
    if (!`${task.code} ${task.title}`.toLowerCase().includes(q)) return false
  }
  return true
}

/** Where a task's source record lives, e.g. the meeting an action came from. */
export function sourceLink(task: Task): string | null {
  if (!task.entity_type || !task.entity_id) return null
  const base = `/${task.entity_type.replace(/_/g, '-')}s?project=${task.project_id}`
  return task.entity_type === 'meeting'
    ? `${base}&meeting=${task.entity_id}`
    : `${base}&id=${task.entity_id}`
}

export function formatDate(value?: string | null) {
  if (!value) return ''
  const [y, m, d] = value.split('-').map(Number)
  return new Date(y, m - 1, d).toLocaleDateString(undefined, {
    day: 'numeric',
    month: 'short',
  })
}
