import { useCallback, useMemo, useState } from 'react'
import { Plus, Search } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useCurrentProject } from '@/stores/use-current-project'
import { can, useSession } from '@/lib/session'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Page } from '@/components/layout/page'
import { statusLabel } from '@/components/records/status'
import { type Task, useBoard, useTask } from './api'
import {
  type Filters,
  NO_FILTERS,
  PRIORITIES,
  TYPES,
  matches,
} from './constants'
import { useRecordParam } from './deep-link'
import { Kanban } from './kanban'
import { TaskCalendar } from './task-calendar'
import { TaskList } from './task-list'
import { TaskSheet } from './task-sheet'

const VIEW_KEY = 'tasks.view'

function readView() {
  try {
    return localStorage.getItem(VIEW_KEY) ?? 'kanban'
  } catch {
    return 'kanban'
  }
}

function FilterBar({
  filters,
  onChange,
}: {
  filters: Filters
  onChange: (f: Filters) => void
}) {
  const { t } = useTranslation()
  const set = (patch: Partial<Filters>) => onChange({ ...filters, ...patch })
  return (
    <div className='flex flex-wrap items-center gap-2'>
      <div className='relative'>
        <Search className='absolute start-2 top-2 size-4 text-muted-foreground' />
        <Input
          className='h-8 w-56 ps-8'
          placeholder={t('tasks.search')}
          value={filters.search}
          onChange={(e) => set({ search: e.target.value })}
        />
      </div>
      <Select
        value={filters.mine ? 'me' : 'anyone'}
        onValueChange={(v) => set({ mine: v === 'me' })}
      >
        <SelectTrigger size='sm' aria-label={t('tasks.assignee')}>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value='anyone'>{t('tasks.anyone')}</SelectItem>
          <SelectItem value='me'>{t('tasks.mine')}</SelectItem>
        </SelectContent>
      </Select>
      <Select value={filters.type} onValueChange={(type) => set({ type })}>
        <SelectTrigger size='sm' aria-label={t('tasks.type')}>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value='all'>{t('tasks.all_types')}</SelectItem>
          {TYPES.map((v) => (
            <SelectItem key={v} value={v}>
              {statusLabel(v)}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <Select
        value={filters.priority}
        onValueChange={(priority) => set({ priority })}
      >
        <SelectTrigger size='sm' aria-label={t('tasks.priority')}>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value='all'>{t('tasks.all_priorities')}</SelectItem>
          {PRIORITIES.map((v) => (
            <SelectItem key={v} value={v}>
              {statusLabel(v)}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <label className='flex items-center gap-2 text-sm'>
        <Switch
          checked={filters.overdue}
          onCheckedChange={(overdue) => set({ overdue })}
        />
        {t('tasks.overdue_only')}
      </label>
    </div>
  )
}

function Workspace({ projectId }: { projectId: number }) {
  const { t } = useTranslation()
  const session = useSession()
  const { data: board } = useBoard(projectId)
  const [view, setView] = useState(readView)
  const [filters, setFilters] = useState<Filters>(NO_FILTERS)
  const [openId, setOpenId] = useRecordParam('task')
  const [creating, setCreating] = useState(false)
  const all = useMemo(
    () => board?.columns.flatMap((c) => c.tasks) ?? [],
    [board]
  )
  const visible = useCallback(
    (task: Task) => matches(task, filters, session.id),
    [filters, session.id]
  )
  const shown = useMemo(() => all.filter(visible), [all, visible])
  const fromBoard = all.find((task) => task.id === openId) ?? null
  const { data: fetched } = useTask(fromBoard ? null : openId)
  const openTask =
    fromBoard ?? (fetched && fetched.project_id === projectId ? fetched : null)
  const open = useCallback((task: Task) => setOpenId(task.id), [setOpenId])
  const editable = can(session, 'tasks.update')

  return (
    <>
      <div className='flex flex-wrap items-center justify-between gap-2'>
        <FilterBar filters={filters} onChange={setFilters} />
        {can(session, 'tasks.create') ? (
          <Button size='sm' onClick={() => setCreating(true)}>
            <Plus /> {t('tasks.new')}
          </Button>
        ) : null}
      </div>
      <Tabs
        value={view}
        onValueChange={(v) => {
          setView(v)
          try {
            localStorage.setItem(VIEW_KEY, v)
          } catch {
            /* the view is only a convenience */
          }
        }}
        className='flex min-h-0 flex-1 flex-col'
      >
        <TabsList>
          <TabsTrigger value='kanban'>{t('tasks.kanban')}</TabsTrigger>
          <TabsTrigger value='list'>{t('tasks.list')}</TabsTrigger>
          <TabsTrigger value='calendar'>{t('tasks.calendar')}</TabsTrigger>
        </TabsList>
        {board ? (
          <>
            <TabsContent value='kanban' className='flex flex-col gap-2'>
              <Kanban
                board={board}
                projectId={projectId}
                visible={visible}
                editable={editable}
                onOpen={open}
              />
            </TabsContent>
            <TabsContent value='list'>
              <TaskList
                tasks={shown}
                projectId={projectId}
                editable={editable}
                onOpen={open}
              />
            </TabsContent>
            <TabsContent value='calendar'>
              <TaskCalendar tasks={shown} onOpen={open} />
            </TabsContent>
          </>
        ) : (
          <p className='text-sm text-muted-foreground'>{t('common.loading')}</p>
        )}
      </Tabs>
      {openTask || creating ? (
        <TaskSheet
          key={creating ? 'new' : openTask?.id}
          open
          task={creating ? null : openTask}
          projectId={projectId}
          typeFields={board?.type_fields ?? {}}
          onClose={() => {
            setCreating(false)
            setOpenId(null)
          }}
        />
      ) : null}
    </>
  )
}

export default function TasksPage() {
  const { t } = useTranslation()
  const project = useCurrentProject()
  return (
    <Page
      title={t('tasks.title')}
      description={t('tasks.description_text')}
      projectScoped
    >
      {project ? (
        <Workspace key={project.id} projectId={project.id} />
      ) : (
        <p className='text-sm text-muted-foreground'>{t('tasks.no_project')}</p>
      )}
    </Page>
  )
}
