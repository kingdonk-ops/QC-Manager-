import { type DragEvent, type ReactNode, useMemo, useState } from 'react'
import { Download, GripVertical, Save, X } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useCurrentProject } from '@/stores/use-current-project'
import { can, useSession } from '@/lib/session'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Page } from '@/components/layout/page'
import {
  type Agg,
  type ColumnInfo,
  type DatasetInfo,
  type PivotRequest,
  type PivotValue,
  type Section,
  useDatasets,
  useDownload,
  usePivot,
  useSaveTemplate,
  useTemplates,
} from './api'
import { ChartView, PivotTable } from './charts'
import {
  type ChartType,
  type FilterRow,
  OPS,
  type Op,
  chartSeries,
  toFilters,
} from './lib'

const AGGS: Agg[] = ['sum', 'avg', 'count', 'min', 'max']
type Zone = 'rows' | 'columns' | 'values' | 'filters'
const NONE = '__none__'

function Chip({
  label,
  onRemove,
  children,
  draggable,
  onDragStart,
}: {
  label: string
  onRemove?: () => void
  children?: ReactNode
  draggable?: boolean
  onDragStart?: (e: DragEvent) => void
}) {
  return (
    <span
      draggable={draggable}
      onDragStart={onDragStart}
      className={cn(
        'inline-flex items-center gap-1 rounded-md border bg-background px-2 py-1 text-xs',
        draggable && 'cursor-grab'
      )}
    >
      {draggable ? (
        <GripVertical className='size-3 text-muted-foreground' />
      ) : null}
      {label}
      {children}
      {onRemove ? (
        <button
          type='button'
          aria-label={`Remove ${label}`}
          className='text-muted-foreground hover:text-foreground'
          onClick={onRemove}
        >
          <X className='size-3' />
        </button>
      ) : null}
    </span>
  )
}

function DropZone({
  title,
  zone,
  columns,
  onDrop,
  children,
}: {
  title: string
  zone: Zone
  columns: ColumnInfo[]
  onDrop: (zone: Zone, key: string) => void
  children: ReactNode
}) {
  const [over, setOver] = useState(false)
  return (
    <div
      data-zone={zone}
      onDragOver={(e) => {
        e.preventDefault()
        setOver(true)
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        e.preventDefault()
        setOver(false)
        const key = e.dataTransfer.getData('text/plain')
        if (key) onDrop(zone, key)
      }}
      className={cn(
        'flex min-h-16 flex-col gap-2 rounded-md border border-dashed p-2',
        over && 'border-primary bg-primary/5'
      )}
    >
      <div className='flex items-center justify-between gap-2'>
        <span className='text-xs font-semibold text-muted-foreground uppercase'>
          {title}
        </span>
        <Select value='' onValueChange={(key) => onDrop(zone, key)}>
          <SelectTrigger
            size='sm'
            className='h-6 w-24 text-xs'
            aria-label={`Add to ${title}`}
          >
            <SelectValue placeholder='Add…' />
          </SelectTrigger>
          <SelectContent>
            {zone === 'values' ? (
              <SelectItem value='*'>Rows (count)</SelectItem>
            ) : null}
            {columns.map((c) => (
              <SelectItem key={c.key} value={c.key}>
                {c.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div className='flex flex-wrap gap-1'>{children}</div>
    </div>
  )
}

function SaveDialog({
  section,
  open,
  onOpenChange,
}: {
  section: Section
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const { t } = useTranslation()
  const { data: templates = [] } = useTemplates()
  const save = useSaveTemplate()
  const custom = templates.filter((tpl) => !tpl.builtin_key)
  const [target, setTarget] = useState<string>('new')
  const [name, setName] = useState('')
  const submit = () => {
    const existing = custom.find((tpl) => String(tpl.id) === target)
    const body = existing
      ? {
          name: existing.name,
          description: existing.description,
          sections: [...existing.sections, section],
          branding: existing.branding,
          landscape: existing.landscape,
        }
      : {
          name: name || section.title || 'New report',
          sections: [section],
          landscape: false,
        }
    save.mutate(
      { id: existing?.id, body },
      { onSuccess: () => onOpenChange(false) }
    )
  }
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('reporting.save_view')}</DialogTitle>
        </DialogHeader>
        <div className='grid gap-3'>
          <Label>{t('reporting.add_to')}</Label>
          <Select value={target} onValueChange={setTarget}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value='new'>{t('reporting.new_template')}</SelectItem>
              {custom.map((tpl) => (
                <SelectItem key={tpl.id} value={String(tpl.id)}>
                  {tpl.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {target === 'new' ? (
            <Input
              placeholder={t('reporting.template_name')}
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          ) : null}
        </div>
        <DialogFooter>
          <Button onClick={submit} disabled={save.isPending}>
            <Save /> {t('common.save')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function Explorer({
  datasets,
  projectId,
}: {
  datasets: DatasetInfo[]
  projectId?: number
}) {
  const { t } = useTranslation()
  const session = useSession()
  const [name, setName] = useState(datasets[0]?.name ?? '')
  const dataset = datasets.find((d) => d.name === name)
  const columns = useMemo(() => dataset?.columns ?? [], [dataset])
  const labels = useMemo(
    () => Object.fromEntries(columns.map((c) => [c.key, c.label])),
    [columns]
  )
  const [rows, setRows] = useState<string[]>([])
  const [cols, setCols] = useState<string[]>([])
  const [values, setValues] = useState<PivotValue[]>([])
  const [filters, setFilters] = useState<FilterRow[]>([])
  const [tab, setTab] = useState('pivot')
  const [chart, setChart] = useState<{
    type: ChartType
    x: string
    y: string[]
    agg: Agg
    group: string
  }>({ type: 'bar', x: '', y: [], agg: 'sum', group: '' })
  const [saving, setSaving] = useState(false)
  const download = useDownload()

  const reset = (next: string) => {
    setName(next)
    setRows([])
    setCols([])
    setValues([])
    setFilters([])
    setChart({ type: 'bar', x: '', y: [], agg: 'sum', group: '' })
  }

  const drop = (zone: Zone, key: string) => {
    if (zone === 'rows' && !rows.includes(key)) setRows([...rows, key])
    if (zone === 'columns' && !cols.includes(key)) setCols([...cols, key])
    if (zone === 'values') {
      const numeric = columns.find((c) => c.key === key)?.aggregatable
      setValues([
        ...values,
        { field: key, agg: key === '*' || !numeric ? 'count' : 'sum' },
      ])
    }
    if (zone === 'filters')
      setFilters([...filters, { field: key, op: 'eq', value: '' }])
  }

  const project = dataset?.project_scoped ? projectId : undefined
  const filterObject = useMemo(() => toFilters(filters), [filters])
  const pivotRequest: PivotRequest | null =
    dataset && (!dataset.project_scoped || projectId)
      ? {
          dataset: dataset.name,
          project_id: project,
          rows,
          columns: cols,
          values,
          filters: filterObject,
        }
      : null
  const chartRequest: PivotRequest | null =
    pivotRequest && chart.x
      ? {
          ...pivotRequest,
          rows: [chart.x],
          columns: chart.group ? [chart.group] : [],
          values: (chart.y.length ? chart.y : ['*']).map((f) => ({
            field: f,
            agg: f === '*' ? 'count' : chart.agg,
          })),
        }
      : null
  const pivot = usePivot(tab === 'pivot' ? pivotRequest : null)
  const charted = usePivot(tab === 'chart' ? chartRequest : null)
  const series = charted.data
    ? chartSeries(charted.data, (f, agg) =>
        f === '*' ? 'Rows' : `${labels[f] ?? f} (${agg})`
      )
    : null

  const section: Section | null = !dataset
    ? null
    : tab === 'chart' && chart.x
      ? {
          type: 'chart',
          title: `${dataset.title}: ${labels[chart.x] ?? chart.x}`,
          dataset: dataset.name,
          chart: chart.type,
          x: chart.x,
          y: chart.y.length ? chart.y : ['*'],
          agg: chart.agg,
          group_by: chart.group || null,
          filters: filterObject,
        }
      : {
          type: 'pivot',
          title: `${dataset.title} pivot`,
          dataset: dataset.name,
          rows,
          columns: cols,
          values,
          filters: filterObject,
        }

  if (!datasets.length)
    return (
      <p className='text-sm text-muted-foreground'>
        {t('reporting.no_datasets')}
      </p>
    )

  return (
    <div className='grid gap-4 lg:grid-cols-[18rem_1fr]'>
      <Card className='self-start'>
        <CardHeader>
          <CardTitle className='text-sm'>{t('reporting.dataset')}</CardTitle>
        </CardHeader>
        <CardContent className='grid gap-3'>
          <Select value={name} onValueChange={reset}>
            <SelectTrigger aria-label={t('reporting.dataset')}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {datasets.map((d) => (
                <SelectItem key={d.name} value={d.name}>
                  {d.title}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {dataset?.project_scoped && !projectId ? (
            <p className='text-xs text-amber-600'>
              {t('reporting.choose_project')}
            </p>
          ) : null}
          <p className='text-xs text-muted-foreground'>
            {t('reporting.drag_hint')}
          </p>
          <div className='flex flex-wrap gap-1'>
            {columns.map((c) => (
              <Chip
                key={c.key}
                label={c.label}
                draggable
                onDragStart={(e) => e.dataTransfer.setData('text/plain', c.key)}
              />
            ))}
          </div>
          <DropZone
            title={t('reporting.filters')}
            zone='filters'
            columns={columns}
            onDrop={drop}
          >
            {filters.map((f, i) => (
              <div key={i} className='flex w-full items-center gap-1'>
                <span className='w-20 truncate text-xs'>
                  {labels[f.field] ?? f.field}
                </span>
                <select
                  aria-label='Operator'
                  className='h-7 rounded border bg-background px-1 text-xs'
                  value={f.op}
                  onChange={(e) =>
                    setFilters(
                      filters.map((x, j) =>
                        j === i ? { ...x, op: e.target.value as Op } : x
                      )
                    )
                  }
                >
                  {OPS.map((op) => (
                    <option key={op} value={op}>
                      {op}
                    </option>
                  ))}
                </select>
                <Input
                  className='h-7 flex-1 text-xs'
                  value={f.value}
                  onChange={(e) =>
                    setFilters(
                      filters.map((x, j) =>
                        j === i ? { ...x, value: e.target.value } : x
                      )
                    )
                  }
                />
                <button
                  type='button'
                  aria-label='Remove filter'
                  onClick={() => setFilters(filters.filter((_, j) => j !== i))}
                >
                  <X className='size-3' />
                </button>
              </div>
            ))}
          </DropZone>
        </CardContent>
      </Card>

      <div className='flex min-w-0 flex-col gap-4'>
        <Tabs value={tab} onValueChange={setTab}>
          <div className='flex flex-wrap items-center gap-2'>
            <TabsList>
              <TabsTrigger value='pivot'>{t('reporting.pivot')}</TabsTrigger>
              <TabsTrigger value='chart'>{t('reporting.chart')}</TabsTrigger>
            </TabsList>
            <div className='ms-auto flex gap-2'>
              {tab === 'pivot' && can(session, 'reporting.export') ? (
                <Button
                  size='sm'
                  variant='outline'
                  disabled={!pivotRequest || download.isPending}
                  onClick={() =>
                    download.mutate({
                      url: '/api/v1/reporting/pivot/export',
                      body: { ...pivotRequest, format: 'xlsx' },
                    })
                  }
                >
                  <Download /> {t('reporting.export_excel')}
                </Button>
              ) : null}
              {can(session, 'reporting.create') ? (
                <Button
                  size='sm'
                  variant='outline'
                  disabled={!section || (tab === 'chart' && !chart.x)}
                  onClick={() => setSaving(true)}
                >
                  <Save /> {t('reporting.save_view')}
                </Button>
              ) : null}
            </div>
          </div>
          <TabsContent value='pivot' className='mt-3 flex flex-col gap-3'>
            <div className='grid gap-2 md:grid-cols-3'>
              <DropZone
                title={t('reporting.rows')}
                zone='rows'
                columns={columns}
                onDrop={drop}
              >
                {rows.map((k) => (
                  <Chip
                    key={k}
                    label={labels[k] ?? k}
                    onRemove={() => setRows(rows.filter((r) => r !== k))}
                  />
                ))}
              </DropZone>
              <DropZone
                title={t('reporting.columns')}
                zone='columns'
                columns={columns}
                onDrop={drop}
              >
                {cols.map((k) => (
                  <Chip
                    key={k}
                    label={labels[k] ?? k}
                    onRemove={() => setCols(cols.filter((r) => r !== k))}
                  />
                ))}
              </DropZone>
              <DropZone
                title={t('reporting.values')}
                zone='values'
                columns={columns}
                onDrop={drop}
              >
                {values.map((v, i) => (
                  <Chip
                    key={i}
                    label={
                      v.field === '*' ? 'Rows' : (labels[v.field] ?? v.field)
                    }
                    onRemove={() => setValues(values.filter((_, j) => j !== i))}
                  >
                    <select
                      aria-label='Aggregation'
                      className='rounded bg-transparent text-xs'
                      value={v.agg}
                      onChange={(e) =>
                        setValues(
                          values.map((x, j) =>
                            j === i ? { ...x, agg: e.target.value as Agg } : x
                          )
                        )
                      }
                    >
                      {(v.field === '*' ? (['count'] as Agg[]) : AGGS).map(
                        (a) => (
                          <option key={a} value={a}>
                            {a}
                          </option>
                        )
                      )}
                    </select>
                  </Chip>
                ))}
              </DropZone>
            </div>
            {pivot.data ? (
              <PivotTable result={pivot.data} labels={labels} />
            ) : pivot.error ? (
              <p className='text-sm text-red-600'>
                {String(pivot.error.message)}
              </p>
            ) : null}
            {pivot.data ? (
              <p className='text-xs text-muted-foreground'>
                {t('reporting.source_rows', { count: pivot.data.source_rows })}
              </p>
            ) : null}
          </TabsContent>
          <TabsContent value='chart' className='mt-3 flex flex-col gap-3'>
            <div className='flex flex-wrap items-end gap-3'>
              <div className='grid gap-1'>
                <Label className='text-xs'>{t('reporting.chart_type')}</Label>
                <Select
                  value={chart.type}
                  onValueChange={(v) =>
                    setChart({ ...chart, type: v as ChartType })
                  }
                >
                  <SelectTrigger size='sm' className='h-8 w-32'>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {(['bar', 'stacked', 'line', 'area', 'pie'] as const).map(
                      (c) => (
                        <SelectItem key={c} value={c}>
                          {t(`reporting.chart_${c}`)}
                        </SelectItem>
                      )
                    )}
                  </SelectContent>
                </Select>
              </div>
              <div className='grid gap-1'>
                <Label className='text-xs'>{t('reporting.x_axis')}</Label>
                <Select
                  value={chart.x || NONE}
                  onValueChange={(v) =>
                    setChart({ ...chart, x: v === NONE ? '' : v })
                  }
                >
                  <SelectTrigger
                    size='sm'
                    className='h-8 w-40'
                    aria-label={t('reporting.x_axis')}
                  >
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={NONE}>–</SelectItem>
                    {columns.map((c) => (
                      <SelectItem key={c.key} value={c.key}>
                        {c.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className='grid gap-1'>
                <Label className='text-xs'>{t('reporting.aggregate')}</Label>
                <Select
                  value={chart.agg}
                  onValueChange={(v) => setChart({ ...chart, agg: v as Agg })}
                >
                  <SelectTrigger size='sm' className='h-8 w-24'>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {AGGS.map((a) => (
                      <SelectItem key={a} value={a}>
                        {a}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className='grid gap-1'>
                <Label className='text-xs'>{t('reporting.colour_by')}</Label>
                <Select
                  value={chart.group || NONE}
                  onValueChange={(v) =>
                    setChart({ ...chart, group: v === NONE ? '' : v })
                  }
                >
                  <SelectTrigger size='sm' className='h-8 w-40'>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={NONE}>–</SelectItem>
                    {columns.map((c) => (
                      <SelectItem key={c.key} value={c.key}>
                        {c.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className='flex flex-wrap gap-3'>
              <span className='text-xs font-semibold text-muted-foreground uppercase'>
                {t('reporting.y_series')}
              </span>
              {columns
                .filter((c) => c.aggregatable)
                .map((c) => (
                  <label
                    key={c.key}
                    className='flex items-center gap-1 text-xs'
                  >
                    <Checkbox
                      checked={chart.y.includes(c.key)}
                      onCheckedChange={(on) =>
                        setChart({
                          ...chart,
                          y: on
                            ? [...chart.y, c.key]
                            : chart.y.filter((y) => y !== c.key),
                        })
                      }
                    />
                    {c.label}
                  </label>
                ))}
              <span className='text-xs text-muted-foreground'>
                {t('reporting.y_hint')}
              </span>
            </div>
            <Card>
              <CardContent className='pt-4'>
                {series ? (
                  <ChartView
                    type={chart.type}
                    data={series.data}
                    series={series.series}
                    height={340}
                  />
                ) : (
                  <p className='py-10 text-center text-sm text-muted-foreground'>
                    {t('reporting.pick_x')}
                  </p>
                )}
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      </div>
      {section ? (
        <SaveDialog section={section} open={saving} onOpenChange={setSaving} />
      ) : null}
    </div>
  )
}

export default function ExplorePage() {
  const { t } = useTranslation()
  const project = useCurrentProject()
  const { data: datasets, isLoading } = useDatasets(project?.id)
  return (
    <Page
      title={t('reporting.explore')}
      description={t('reporting.explore_description')}
      projectScoped
    >
      {isLoading || !datasets ? (
        <p className='text-sm text-muted-foreground'>{t('common.loading')}</p>
      ) : (
        <Explorer
          key={project?.id ?? 0}
          datasets={datasets}
          projectId={project?.id}
        />
      )}
    </Page>
  )
}
