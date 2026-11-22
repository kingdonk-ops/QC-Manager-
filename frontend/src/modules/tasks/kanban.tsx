import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { Settings2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { ApiError } from '@/api/client'
import { handleServerError } from '@/lib/handle-server-error'
import { cn } from '@/lib/utils'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover'
import { statusLabel } from '@/components/records/status'
import {
  type Board,
  type MoveArgs,
  type Task,
  type TaskStatus,
  taskKeys,
  useMoveTask,
  useSetWipLimits,
} from './api'
import { applyMove } from './board'
import { STATUSES } from './constants'
import { TaskCard } from './task-card'

function isWipRefusal(error: unknown) {
  return (
    error instanceof ApiError &&
    error.status === 422 &&
    typeof error.detail === 'string' &&
    error.detail.includes('WIP')
  )
}

function WipSettings({
  board,
  projectId,
}: {
  board: Board
  projectId: number
}) {
  const { t } = useTranslation()
  const save = useSetWipLimits(projectId)
  const [open, setOpen] = useState(false)
  const [draft, setDraft] = useState<Record<string, string>>({})
  return (
    <Popover
      open={open}
      onOpenChange={(o) => {
        setOpen(o)
        if (o)
          setDraft(
            Object.fromEntries(
              board.columns.map((c) => [c.status, String(c.wip_limit || '')])
            )
          )
      }}
    >
      <PopoverTrigger asChild>
        <Button size='sm' variant='outline'>
          <Settings2 /> {t('tasks.wip_limits')}
        </Button>
      </PopoverTrigger>
      <PopoverContent align='end' className='grid w-64 gap-3'>
        <p className='text-xs text-muted-foreground'>{t('tasks.wip_help')}</p>
        {STATUSES.map((s) => (
          <label key={s} className='flex items-center justify-between gap-2'>
            <span className='text-sm'>{t(`tasks.status.${s}`)}</span>
            <Input
              type='number'
              min={0}
              max={500}
              className='h-8 w-20'
              value={draft[s] ?? ''}
              placeholder='–'
              onChange={(e) => setDraft({ ...draft, [s]: e.target.value })}
            />
          </label>
        ))}
        <Button
          size='sm'
          disabled={save.isPending}
          onClick={() =>
            save.mutate(
              Object.fromEntries(
                STATUSES.map((s) => [s, Math.max(0, Number(draft[s]) || 0)])
              ),
              { onSuccess: () => setOpen(false) }
            )
          }
        >
          {t('common.save')}
        </Button>
      </PopoverContent>
    </Popover>
  )
}

export function Kanban({
  board,
  projectId,
  visible,
  editable,
  onOpen,
}: {
  board: Board
  projectId: number
  visible: (task: Task) => boolean
  editable: boolean
  onOpen: (task: Task) => void
}) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const move = useMoveTask(projectId)
  const [dragId, setDragId] = useState<number | null>(null)
  const [target, setTarget] = useState<{
    status: TaskStatus
    beforeId: number | null
  } | null>(null)
  const [refused, setRefused] = useState<MoveArgs | null>(null)

  const run = (args: MoveArgs) => {
    const key = taskKeys.board(projectId)
    const before = queryClient.getQueryData<Board>(key)
    if (before)
      queryClient.setQueryData(
        key,
        applyMove(before, args.id, args.status, args.before_id)
      )
    move.mutate(args, {
      onError: (error) => {
        if (before) queryClient.setQueryData(key, before)
        if (isWipRefusal(error) && !args.override_wip) setRefused(args)
        else handleServerError(error)
      },
    })
  }

  const dropIndex = (e: React.DragEvent<HTMLDivElement>) => {
    const cards = Array.from(
      e.currentTarget.querySelectorAll<HTMLElement>('[data-task-id]')
    )
    for (const card of cards) {
      const id = Number(card.dataset.taskId)
      if (id === dragId) continue
      const box = card.getBoundingClientRect()
      if (e.clientY < box.top + box.height / 2) return id
    }
    return null
  }

  const finish = () => {
    setDragId(null)
    setTarget(null)
  }

  return (
    <>
      <div className='flex justify-end'>
        {editable ? <WipSettings board={board} projectId={projectId} /> : null}
      </div>
      <div className='grid min-h-0 flex-1 auto-cols-[minmax(240px,1fr)] grid-flow-col gap-3 overflow-x-auto pb-2'>
        {board.columns.map((column) => {
          const count = column.tasks.length
          const limit = column.wip_limit
          const over = limit > 0 && count > limit
          const full = limit > 0 && count === limit
          const shown = column.tasks.filter(visible)
          const isTarget = target?.status === column.status
          return (
            <div
              key={column.status}
              data-testid={`column-${column.status}`}
              className={cn(
                'flex min-h-48 flex-col gap-2 rounded-lg border bg-muted/40 p-2',
                over && 'border-red-500/60 bg-red-500/5',
                isTarget && 'ring-2 ring-primary/40'
              )}
              onDragOver={(e) => {
                if (dragId === null) return
                e.preventDefault()
                e.dataTransfer.dropEffect = 'move'
                const beforeId = dropIndex(e)
                if (
                  target?.status !== column.status ||
                  target.beforeId !== beforeId
                )
                  setTarget({ status: column.status, beforeId })
              }}
              onDragLeave={(e) => {
                if (!e.currentTarget.contains(e.relatedTarget as Node))
                  setTarget(null)
              }}
              onDrop={(e) => {
                e.preventDefault()
                if (dragId === null) return
                const beforeId = dropIndex(e)
                const task = column.tasks.find((t) => t.id === dragId)
                const sameSpot =
                  task &&
                  (beforeId === null
                    ? column.tasks[column.tasks.length - 1]?.id === dragId
                    : column.tasks[
                        column.tasks.findIndex((t) => t.id === beforeId) - 1
                      ]?.id === dragId)
                if (!sameSpot)
                  run({
                    id: dragId,
                    status: column.status,
                    before_id: beforeId,
                  })
                finish()
              }}
            >
              <div className='flex items-center justify-between px-1 text-sm font-medium'>
                <span>{t(`tasks.status.${column.status}`)}</span>
                <span
                  className={cn(
                    'rounded px-1.5 text-xs tabular-nums',
                    over
                      ? 'bg-red-500/15 font-semibold text-red-700 dark:text-red-400'
                      : full
                        ? 'bg-amber-500/15 text-amber-700 dark:text-amber-400'
                        : 'text-muted-foreground'
                  )}
                  title={limit ? t('tasks.wip_limit') : undefined}
                >
                  {limit ? `${count} / ${limit}` : count}
                </span>
              </div>
              {shown.map((task) => (
                <div key={task.id} className='grid gap-2'>
                  {isTarget && target?.beforeId === task.id ? (
                    <div className='h-0.5 rounded bg-primary' />
                  ) : null}
                  <TaskCard
                    task={task}
                    onOpen={() => onOpen(task)}
                    draggable={editable}
                    dragging={dragId === task.id}
                    onDragStart={(e) => {
                      e.dataTransfer.effectAllowed = 'move'
                      e.dataTransfer.setData('text/plain', String(task.id))
                      setDragId(task.id)
                    }}
                    onDragEnd={finish}
                  />
                </div>
              ))}
              {isTarget && target?.beforeId === null ? (
                <div className='h-0.5 rounded bg-primary' />
              ) : null}
              {!shown.length ? (
                <p className='px-1 py-4 text-center text-xs text-muted-foreground'>
                  {t('tasks.empty_column')}
                </p>
              ) : null}
            </div>
          )
        })}
      </div>
      <AlertDialog
        open={refused !== null}
        onOpenChange={(o) => !o && setRefused(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('tasks.wip_reached')}</AlertDialogTitle>
            <AlertDialogDescription>
              {t('tasks.wip_reached_body', {
                column: refused ? statusLabel(refused.status) : '',
              })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                if (refused) run({ ...refused, override_wip: true })
                setRefused(null)
              }}
            >
              {t('tasks.move_anyway')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
      {dragId !== null ? (
        <div className='sr-only' aria-live='polite'>
          {t('tasks.dragging')}
        </div>
      ) : null}
    </>
  )
}
