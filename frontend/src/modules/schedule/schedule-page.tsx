import { useMemo, useRef, useState } from 'react'
import {
  CalendarCog,
  ChevronDown,
  ChevronRight,
  Dices,
  Download,
  Flag,
  Layers,
  Plus,
  RefreshCw,
  Upload,
  Wand2,
} from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { useCurrentProject } from '@/stores/use-current-project'
import { can, useSession } from '@/lib/session'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Page } from '@/components/layout/page'
import { useActiveModules } from '../_runtime'
import { ActivitySheet } from './activity-sheet'
import {
  type Activity,
  type ActivityPatch,
  exportUrl,
  useAddActivity,
  useAddDependency,
  useCalculate,
  useGantt,
  useUpdateActivity,
} from './api'
import {
  BaselineDialog,
  CalendarDialog,
  GenerateDialog,
  ImportDialog,
} from './dialogs'
import { composeSvg, exportPdf, exportPng } from './export-image'
import { GanttChart, TimescaleHeader } from './gantt-chart'
import { barColor, floatOf, isCritical } from './gantt-colors'
import {
  HEADER_HEIGHT,
  ROW_HEIGHT,
  type Zoom,
  ZOOMS,
  chartRange,
  flattenTree,
} from './gantt-math'
import { MonteCarloPanel } from './monte-carlo-panel'

const COLUMNS = [
  { key: 'wbs', width: 92 },
  { key: 'name', width: 210 },
  { key: 'duration', width: 52 },
  { key: 'start', width: 92 },
  { key: 'finish', width: 92 },
  { key: 'percent', width: 52 },
  { key: 'float', width: 52 },
] as const
const GRID_WIDTH = COLUMNS.reduce((sum, c) => sum + c.width, 0)

/** A grid cell that turns into an input on double-click or Enter; commits on Enter or blur. */
function EditCell({
  value,
  display,
  type = 'text',
  editable,
  onCommit,
  className,
  label,
}: {
  value: string
  display?: string
  type?: 'text' | 'number' | 'date'
  editable: boolean
  onCommit: (value: string) => void
  className?: string
  label: string
}) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(value)
  if (editing)
    return (
      <input
        autoFocus
        aria-label={label}
        type={type}
        className='h-6 w-full rounded border bg-background px-1 text-xs'
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={() => {
          setEditing(false)
          if (draft !== value && draft !== '') onCommit(draft)
        }}
        onKeyDown={(e) => {
          if (e.key === 'Enter') e.currentTarget.blur()
          if (e.key === 'Escape') {
            setDraft(value)
            setEditing(false)
          }
        }}
      />
    )
  return (
    <div
      role={editable ? 'button' : undefined}
      tabIndex={editable ? 0 : undefined}
      aria-label={editable ? label : undefined}
      className={cn('truncate', editable && 'cursor-text', className)}
      onDoubleClick={() => {
        if (!editable) return
        setDraft(value)
        setEditing(true)
      }}
      onKeyDown={(e) => {
        if (editable && e.key === 'Enter') {
          setDraft(value)
          setEditing(true)
        }
      }}
    >
      {display ?? value}
    </div>
  )
}

function shortDate(iso?: string | null) {
  if (!iso) return '–'
  const [y, m, d] = iso.split('-')
  return `${d}/${m}/${y.slice(2)}`
}

function Kpi({
  label,
  value,
  tone,
}: {
  label: string
  value: string
  tone?: 'bad' | 'good'
}) {
  return (
    <Card className='gap-1 py-3'>
      <CardHeader className='px-4'>
        <CardTitle className='text-xs font-medium text-muted-foreground'>
          {label}
        </CardTitle>
      </CardHeader>
      <CardContent className='px-4'>
        <p
          className={cn(
            'text-lg font-semibold tabular-nums',
            tone === 'bad' && 'text-red-600',
            tone === 'good' && 'text-green-600'
          )}
        >
          {value}
        </p>
      </CardContent>
    </Card>
  )
}

function Schedule({
  projectId,
  projectName,
}: {
  projectId: number
  projectName: string
}) {
  const { t } = useTranslation()
  const session = useSession()
  const canEdit = can(session, 'schedule.update')
  const canCreate = can(session, 'schedule.create')
  const canImport = can(session, 'schedule.import')
  const canExport = can(session, 'schedule.export')
  const cvrOn = useActiveModules().some((m) => m.id === 'cvr')
  const { data: gantt, isLoading } = useGantt(projectId)
  const update = useUpdateActivity(projectId)
  const addActivity = useAddActivity(projectId)
  const link = useAddDependency(projectId)
  const calculate = useCalculate(projectId)

  const [zoom, setZoom] = useState<Zoom>('week')
  const [collapsed, setCollapsed] = useState<Set<number>>(new Set())
  const [selected, setSelected] = useState<number | null>(null)
  const [open, setOpen] = useState<number | null>(null)
  const [showBaseline, setShowBaseline] = useState(true)
  const [panel, setPanel] = useState<
    null | 'import' | 'baselines' | 'calendar' | 'generate' | 'mc'
  >(null)
  const [newName, setNewName] = useState('')
  const headerRef = useRef<SVGSVGElement>(null)
  const bodyRef = useRef<SVGSVGElement>(null)

  const activities = useMemo(() => gantt?.activities ?? [], [gantt])
  const rows = useMemo(
    () => flattenTree(activities, collapsed),
    [activities, collapsed]
  )
  const range = useMemo(
    () =>
      chartRange(
        activities.flatMap((a) => [
          a.early_start,
          a.early_finish,
          a.baseline_start,
          a.baseline_finish,
        ]),
        zoom
      ),
    [activities, zoom]
  )

  const patch = (a: Activity, body: ActivityPatch) =>
    update.mutate({ id: a.id, patch: body })

  const toggle = (id: number) => {
    const next = new Set(collapsed)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    setCollapsed(next)
  }

  const exportImage = async (kind: 'png' | 'pdf') => {
    if (!headerRef.current || !bodyRef.current) return
    const composed = composeSvg(
      headerRef.current,
      bodyRef.current,
      rows.map((r) => ({
        wbs: r.item.wbs_code,
        name: r.item.name,
        depth: r.depth,
      })),
      `${projectName} — ${t('schedule.title')}`
    )
    try {
      if (kind === 'png') await exportPng(composed, `schedule-${projectId}.png`)
      else exportPdf(composed, `${projectName} schedule`)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : String(error))
    }
  }

  const summary = gantt?.summary
  const openActivity = activities.find((a) => a.id === open)
  const variance = summary?.finish_variance

  return (
    <>
      <div className='grid grid-cols-2 gap-3 lg:grid-cols-5'>
        <Kpi
          label={t('schedule.kpi.start')}
          value={shortDate(summary?.start)}
        />
        <Kpi
          label={t('schedule.kpi.finish')}
          value={shortDate(summary?.finish)}
        />
        <Kpi
          label={t('schedule.kpi.vs_baseline')}
          value={
            variance == null
              ? '–'
              : `${variance > 0 ? '+' : ''}${variance} ${t('schedule.days')}`
          }
          tone={variance == null ? undefined : variance > 0 ? 'bad' : 'good'}
        />
        <Kpi
          label={t('schedule.kpi.progress')}
          value={`${Math.round(summary?.percent_complete ?? 0)}%`}
        />
        <Kpi
          label={t('schedule.kpi.critical')}
          value={`${summary?.critical_count ?? 0} / ${summary?.activity_count ?? 0}`}
        />
      </div>

      <div className='flex flex-wrap items-center gap-2'>
        {canCreate ? (
          <form
            className='flex items-center gap-2'
            onSubmit={(e) => {
              e.preventDefault()
              const parent = activities.find((a) => a.id === selected)
              addActivity.mutate(
                {
                  name: newName,
                  duration: 5,
                  parent_id: parent?.type === 'summary' ? parent.id : null,
                  predecessor_id:
                    parent && parent.type !== 'summary' ? parent.id : null,
                },
                { onSuccess: () => setNewName('') }
              )
            }}
          >
            <Input
              className='h-8 w-56'
              placeholder={t('schedule.new_activity')}
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              required
              maxLength={300}
            />
            <Button size='sm' type='submit' disabled={addActivity.isPending}>
              <Plus /> {t('schedule.add')}
            </Button>
          </form>
        ) : null}
        <Select value={zoom} onValueChange={(v) => setZoom(v as Zoom)}>
          <SelectTrigger
            size='sm'
            className='h-8 w-32'
            aria-label={t('schedule.zoom')}
          >
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {ZOOMS.map((z) => (
              <SelectItem key={z} value={z}>
                {t(`schedule.zooms.${z}`)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <label className='flex items-center gap-1.5 text-sm'>
          <Checkbox
            checked={showBaseline}
            onCheckedChange={(v) => setShowBaseline(v === true)}
          />
          {t('schedule.show_baseline')}
        </label>
        <div className='ms-auto flex flex-wrap gap-2'>
          {canEdit ? (
            <Button
              size='sm'
              variant='outline'
              onClick={() => calculate.mutate()}
              disabled={calculate.isPending}
            >
              <RefreshCw /> {t('schedule.calculate')}
            </Button>
          ) : null}
          <Button size='sm' variant='outline' onClick={() => setPanel('mc')}>
            <Dices /> {t('schedule.mc.button')}
          </Button>
          {canEdit ? (
            <Button
              size='sm'
              variant='outline'
              onClick={() => setPanel('baselines')}
            >
              <Flag /> {t('schedule.baselines.button')}
            </Button>
          ) : null}
          {canEdit && gantt ? (
            <Button
              size='sm'
              variant='outline'
              onClick={() => setPanel('calendar')}
            >
              <CalendarCog /> {t('schedule.calendar.button')}
            </Button>
          ) : null}
          {canCreate ? (
            <Button
              size='sm'
              variant='outline'
              onClick={() => setPanel('generate')}
            >
              <Wand2 /> {t('schedule.generate.button')}
            </Button>
          ) : null}
          {canImport ? (
            <Button
              size='sm'
              variant='outline'
              onClick={() => setPanel('import')}
            >
              <Upload /> {t('schedule.import.button')}
            </Button>
          ) : null}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button size='sm' variant='outline'>
                <Download /> {t('schedule.export')}
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align='end'>
              <DropdownMenuItem onSelect={() => void exportImage('png')}>
                PNG
              </DropdownMenuItem>
              <DropdownMenuItem onSelect={() => void exportImage('pdf')}>
                PDF ({t('schedule.via_print')})
              </DropdownMenuItem>
              {canExport ? (
                <>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem asChild>
                    <a href={exportUrl(projectId, 'msp_xml')}>MS Project XML</a>
                  </DropdownMenuItem>
                  <DropdownMenuItem asChild>
                    <a href={exportUrl(projectId, 'xlsx')}>Excel</a>
                  </DropdownMenuItem>
                  <DropdownMenuItem asChild>
                    <a href={exportUrl(projectId, 'csv')}>CSV</a>
                  </DropdownMenuItem>
                </>
              ) : null}
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>

      <div className='relative h-[calc(100vh-22rem)] min-h-[420px] overflow-auto rounded-md border bg-background'>
        <div className='flex w-max'>
          <div
            className='sticky left-0 z-20 shrink-0 border-e bg-background text-xs'
            style={{ width: GRID_WIDTH }}
          >
            <div
              className='sticky top-0 z-30 flex items-end border-b bg-background font-medium text-muted-foreground'
              style={{ height: HEADER_HEIGHT }}
            >
              {COLUMNS.map((c) => (
                <div
                  key={c.key}
                  className={cn(
                    'px-2 pb-1.5',
                    c.key !== 'wbs' && c.key !== 'name' && 'text-right'
                  )}
                  style={{ width: c.width }}
                >
                  {t(`schedule.col.${c.key}`)}
                </div>
              ))}
            </div>
            {rows.map(({ item: a, depth, hasChildren }) => {
              const leaf = a.type !== 'summary'
              return (
                <div
                  key={a.id}
                  className={cn(
                    'flex items-center border-b border-border/40',
                    a.id === selected && 'bg-blue-500/10',
                    a.type === 'summary' && 'font-semibold'
                  )}
                  style={{ height: ROW_HEIGHT }}
                  onClick={() => setSelected(a.id)}
                >
                  <div
                    className='flex items-center gap-0.5 px-1 font-mono'
                    style={{
                      width: COLUMNS[0].width,
                      paddingInlineStart: 4 + depth * 8,
                    }}
                  >
                    {hasChildren ? (
                      <button
                        aria-label={
                          collapsed.has(a.id)
                            ? t('schedule.expand')
                            : t('schedule.collapse')
                        }
                        onClick={(e) => {
                          e.stopPropagation()
                          toggle(a.id)
                        }}
                      >
                        {collapsed.has(a.id) ? (
                          <ChevronRight className='size-3.5' />
                        ) : (
                          <ChevronDown className='size-3.5' />
                        )}
                      </button>
                    ) : (
                      <span className='inline-block w-3.5' />
                    )}
                    <button
                      className='truncate hover:underline'
                      onClick={() => setOpen(a.id)}
                      title={t('schedule.open')}
                    >
                      {a.wbs_code}
                    </button>
                  </div>
                  <div
                    className='flex items-center gap-1 px-2'
                    style={{
                      width: COLUMNS[1].width,
                      paddingInlineStart: 8 + depth * 10,
                    }}
                  >
                    <span
                      className='inline-block size-2 shrink-0 rounded-full'
                      style={{ background: barColor(a) }}
                    />
                    <EditCell
                      label={t('schedule.col.name')}
                      value={a.name}
                      editable={canEdit}
                      onCommit={(v) => patch(a, { name: v })}
                      className='flex-1'
                    />
                    {isCritical(a) && a.status !== 'completed' && leaf ? (
                      <span className='rounded bg-red-600 px-1 text-[9px] font-bold text-white'>
                        CP
                      </span>
                    ) : null}
                  </div>
                  <div
                    className='px-2 text-right tabular-nums'
                    style={{ width: COLUMNS[2].width }}
                  >
                    <EditCell
                      label={t('schedule.col.duration')}
                      type='number'
                      value={String(a.duration)}
                      editable={canEdit && a.type === 'task'}
                      onCommit={(v) =>
                        patch(a, {
                          duration: Math.max(0, Math.round(Number(v))),
                        })
                      }
                    />
                  </div>
                  <div
                    className='px-2 text-right tabular-nums'
                    style={{ width: COLUMNS[3].width }}
                  >
                    <EditCell
                      label={t('schedule.col.start')}
                      type='date'
                      value={a.early_start ?? ''}
                      display={shortDate(a.actual_start ?? a.early_start)}
                      editable={canEdit && leaf}
                      onCommit={(v) => patch(a, { planned_start: v })}
                    />
                  </div>
                  <div
                    className='px-2 text-right tabular-nums'
                    style={{ width: COLUMNS[4].width }}
                  >
                    <EditCell
                      label={t('schedule.col.finish')}
                      type='date'
                      value={a.early_finish ?? ''}
                      display={shortDate(a.actual_finish ?? a.early_finish)}
                      editable={canEdit && a.type === 'task'}
                      onCommit={(v) => patch(a, { planned_finish: v })}
                    />
                  </div>
                  <div
                    className='px-2 text-right tabular-nums'
                    style={{ width: COLUMNS[5].width }}
                  >
                    <EditCell
                      label={t('schedule.col.percent')}
                      type='number'
                      value={String(Math.round(a.percent_complete))}
                      display={`${Math.round(a.percent_complete)}%`}
                      editable={canEdit && leaf}
                      onCommit={(v) =>
                        patch(a, {
                          percent_complete: Math.min(
                            100,
                            Math.max(0, Number(v))
                          ),
                        })
                      }
                    />
                  </div>
                  <div
                    className={cn(
                      'px-2 text-right tabular-nums',
                      (floatOf(a) ?? 0) < 0 && 'text-red-600'
                    )}
                    style={{ width: COLUMNS[6].width }}
                    title={
                      a.p6_float_days != null
                        ? t('schedule.float_p6')
                        : undefined
                    }
                  >
                    {floatOf(a) ?? '–'}
                  </div>
                </div>
              )
            })}
            {!isLoading && rows.length === 0 ? (
              <p className='p-4 text-sm text-muted-foreground'>
                {t('schedule.empty')}
              </p>
            ) : null}
          </div>
          <div className='shrink-0'>
            <div className='sticky top-0 z-10 border-b bg-background'>
              <TimescaleHeader
                zoom={zoom}
                from={range.from}
                to={range.to}
                svgRef={headerRef}
              />
            </div>
            <GanttChart
              rows={rows}
              dependencies={gantt?.dependencies ?? []}
              zoom={zoom}
              from={range.from}
              to={range.to}
              workingDays={gantt?.calendar.working_days ?? [0, 1, 2, 3, 4]}
              holidays={gantt?.calendar.holidays ?? []}
              dataDate={gantt?.calendar.data_date}
              showBaseline={showBaseline}
              editable={canEdit}
              selectedId={selected}
              bodyRef={bodyRef}
              onSelect={setSelected}
              onMove={(id, start) =>
                update.mutate({ id, patch: { planned_start: start } })
              }
              onResize={(id, finish) =>
                update.mutate({ id, patch: { planned_finish: finish } })
              }
              onLink={(pred, succ) =>
                link.mutate({
                  predecessor_id: pred,
                  successor_id: succ,
                  type: 'FS',
                })
              }
            />
          </div>
        </div>
      </div>
      <p className='flex items-center gap-1.5 text-xs text-muted-foreground'>
        <Layers className='size-3.5' /> {t('schedule.hint')}
      </p>

      {openActivity ? (
        <ActivitySheet
          key={openActivity.id}
          activity={openActivity}
          activities={activities}
          dependencies={gantt?.dependencies ?? []}
          projectId={projectId}
          editable={canEdit}
          onClose={() => setOpen(null)}
        />
      ) : null}
      <MonteCarloPanel
        projectId={projectId}
        open={panel === 'mc'}
        onClose={() => setPanel(null)}
      />
      <ImportDialog
        projectId={projectId}
        open={panel === 'import'}
        onClose={() => setPanel(null)}
      />
      <GenerateDialog
        projectId={projectId}
        open={panel === 'generate'}
        onClose={() => setPanel(null)}
        cvrAvailable={cvrOn}
      />
      <BaselineDialog
        projectId={projectId}
        open={panel === 'baselines'}
        onClose={() => setPanel(null)}
        baselines={gantt?.baselines ?? []}
      />
      {gantt && panel === 'calendar' ? (
        <CalendarDialog
          projectId={projectId}
          open
          onClose={() => setPanel(null)}
          calendar={gantt.calendar}
        />
      ) : null}
    </>
  )
}

export default function SchedulePage() {
  const { t } = useTranslation()
  const project = useCurrentProject()
  return (
    <Page
      title={t('schedule.title')}
      description={t('schedule.description')}
      projectScoped
    >
      {project ? (
        <Schedule
          key={project.id}
          projectId={project.id}
          projectName={project.name}
        />
      ) : (
        <p className='text-sm text-muted-foreground'>
          {t('schedule.no_project')}
        </p>
      )}
    </Page>
  )
}
