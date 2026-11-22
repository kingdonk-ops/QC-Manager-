import { useMemo, useState } from 'react'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import type { Task } from './api'
import { monthGrid } from './board'
import { TYPE_COLOURS } from './constants'

const iso = (d: Date) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`

export function TaskCalendar({
  tasks,
  onOpen,
}: {
  tasks: Task[]
  onOpen: (task: Task) => void
}) {
  const { t, i18n } = useTranslation()
  const today = new Date()
  const [cursor, setCursor] = useState({
    year: today.getFullYear(),
    month: today.getMonth(),
  })
  const days = monthGrid(cursor.year, cursor.month)
  const byDay = useMemo(() => {
    const map = new Map<string, Task[]>()
    for (const task of tasks) {
      if (!task.due_date) continue
      map.set(task.due_date, [...(map.get(task.due_date) ?? []), task])
    }
    return map
  }, [tasks])
  const undated = tasks.filter((task) => !task.due_date).length
  const shift = (n: number) =>
    setCursor(({ year, month }) => {
      const d = new Date(year, month + n, 1)
      return { year: d.getFullYear(), month: d.getMonth() }
    })
  const weekdays = days
    .slice(0, 7)
    .map((d) => d.toLocaleDateString(i18n.language, { weekday: 'short' }))

  return (
    <div className='grid gap-2'>
      <div className='flex items-center gap-2'>
        <Button
          size='icon'
          variant='outline'
          className='size-8'
          aria-label={t('tasks.previous_month')}
          onClick={() => shift(-1)}
        >
          <ChevronLeft />
        </Button>
        <Button
          size='icon'
          variant='outline'
          className='size-8'
          aria-label={t('tasks.next_month')}
          onClick={() => shift(1)}
        >
          <ChevronRight />
        </Button>
        <Button
          size='sm'
          variant='ghost'
          onClick={() =>
            setCursor({ year: today.getFullYear(), month: today.getMonth() })
          }
        >
          {t('tasks.today')}
        </Button>
        <h3 className='font-medium'>
          {new Date(cursor.year, cursor.month, 1).toLocaleDateString(
            i18n.language,
            { month: 'long', year: 'numeric' }
          )}
        </h3>
        {undated ? (
          <span className='ms-auto text-xs text-muted-foreground'>
            {t('tasks.undated', { count: undated })}
          </span>
        ) : null}
      </div>
      <div className='grid grid-cols-7 overflow-hidden rounded-lg border text-sm'>
        {weekdays.map((w) => (
          <div
            key={w}
            className='border-b bg-muted/50 px-2 py-1 text-xs font-medium text-muted-foreground'
          >
            {w}
          </div>
        ))}
        {days.map((day) => {
          const key = iso(day)
          const inMonth = day.getMonth() === cursor.month
          const isToday = key === iso(today)
          const items = byDay.get(key) ?? []
          return (
            <div
              key={key}
              className={cn(
                'min-h-24 border-e border-b p-1 [&:nth-child(7n)]:border-e-0',
                !inMonth && 'bg-muted/30 text-muted-foreground'
              )}
            >
              <div
                className={cn(
                  'mb-1 w-fit rounded px-1 text-xs tabular-nums',
                  isToday && 'bg-primary text-primary-foreground'
                )}
              >
                {day.getDate()}
              </div>
              <div className='grid gap-0.5'>
                {items.slice(0, 4).map((task) => (
                  <button
                    key={task.id}
                    type='button'
                    onClick={() => onOpen(task)}
                    title={`${task.code} ${task.title}`}
                    className={cn(
                      'flex items-center gap-1 truncate rounded px-1 py-0.5 text-start text-xs hover:bg-accent',
                      task.overdue && 'text-red-600 dark:text-red-400',
                      task.status === 'done' && 'line-through opacity-60'
                    )}
                  >
                    <span
                      className={cn(
                        'size-1.5 shrink-0 rounded-full',
                        TYPE_COLOURS[task.type]
                      )}
                    />
                    <span className='truncate'>{task.title}</span>
                  </button>
                ))}
                {items.length > 4 ? (
                  <span className='px-1 text-xs text-muted-foreground'>
                    {t('tasks.more', { count: items.length - 4 })}
                  </span>
                ) : null}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
