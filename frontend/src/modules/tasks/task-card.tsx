import { CalendarDays } from 'lucide-react'
import { initials } from '@/lib/session'
import { cn } from '@/lib/utils'
import type { Task } from './api'
import { PRIORITY_TEXT, TYPE_COLOURS, formatDate } from './constants'

export function TaskCard({
  task,
  onOpen,
  draggable,
  onDragStart,
  onDragEnd,
  dragging,
}: {
  task: Task
  onOpen: () => void
  draggable?: boolean
  onDragStart?: (e: React.DragEvent) => void
  onDragEnd?: () => void
  dragging?: boolean
}) {
  return (
    <button
      type='button'
      draggable={draggable}
      onDragStart={onDragStart}
      onDragEnd={onDragEnd}
      onClick={onOpen}
      data-task-id={task.id}
      className={cn(
        'relative grid w-full gap-1.5 overflow-hidden rounded-md border bg-card py-2 ps-3 pe-2 text-start text-sm shadow-xs transition hover:border-primary/50',
        draggable && 'cursor-grab active:cursor-grabbing',
        dragging && 'opacity-40'
      )}
    >
      <span
        className={cn(
          'absolute inset-y-0 start-0 w-1',
          TYPE_COLOURS[task.type] ?? 'bg-slate-400'
        )}
        aria-hidden
      />
      <span className='flex items-center justify-between gap-2 text-xs text-muted-foreground'>
        <span className='font-mono'>{task.code}</span>
        <span className='capitalize'>{task.type}</span>
      </span>
      <span className='line-clamp-3 leading-snug font-medium'>
        {task.title}
      </span>
      <span className='flex items-center justify-between gap-2 text-xs'>
        <span
          className={cn('font-medium capitalize', PRIORITY_TEXT[task.priority])}
        >
          {task.priority}
        </span>
        <span className='flex items-center gap-2'>
          {task.due_date ? (
            <span
              className={cn(
                'flex items-center gap-1',
                task.overdue
                  ? 'font-medium text-red-600 dark:text-red-400'
                  : 'text-muted-foreground'
              )}
            >
              <CalendarDays className='size-3' />
              {formatDate(task.due_date)}
            </span>
          ) : null}
          {task.assignee_name ? (
            <span
              title={task.assignee_name}
              className='grid size-6 place-items-center rounded-full bg-muted text-[10px] font-semibold'
            >
              {initials(task.assignee_name)}
            </span>
          ) : null}
        </span>
      </span>
    </button>
  )
}
