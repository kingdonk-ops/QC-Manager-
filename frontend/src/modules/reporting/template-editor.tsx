import { type ReactNode, useState } from 'react'
import {
  ArrowDown,
  ArrowUp,
  BarChart3,
  Gauge,
  GripVertical,
  Plus,
  Table2,
  Trash2,
  Type,
  Grid3x3,
} from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
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
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import { uploadFile } from '@/components/records/files'
import {
  type Agg,
  type DatasetInfo,
  type Section,
  type Template,
  type TemplateIn,
  useDatasets,
  useKpiDefinitions,
  useSaveTemplate,
} from './api'

type Kind = Section['type']
const NONE = '__none__'
const AGGS: Agg[] = ['sum', 'avg', 'count', 'min', 'max']

const PALETTE: { kind: Kind; icon: typeof Gauge }[] = [
  { kind: 'kpis', icon: Gauge },
  { kind: 'table', icon: Table2 },
  { kind: 'chart', icon: BarChart3 },
  { kind: 'pivot', icon: Grid3x3 },
  { kind: 'text', icon: Type },
]

function blank(kind: Kind, dataset: string): Section {
  switch (kind) {
    case 'kpis':
      return { type: 'kpis', title: 'Key figures', keys: [] }
    case 'table':
      return {
        type: 'table',
        title: '',
        dataset,
        columns: [],
        filters: {},
        group_by: null,
        sort_by: null,
        descending: false,
        limit: 500,
      }
    case 'chart':
      return {
        type: 'chart',
        title: '',
        dataset,
        chart: 'bar',
        x: '',
        y: [],
        agg: 'sum',
        group_by: null,
        filters: {},
      }
    case 'pivot':
      return {
        type: 'pivot',
        title: '',
        dataset,
        rows: [],
        columns: [],
        values: [{ field: '*', agg: 'count' }],
        filters: {},
      }
    default:
      return { type: 'text', title: '', body: '' }
  }
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className='grid gap-1'>
      <Label className='text-xs text-muted-foreground'>{label}</Label>
      {children}
    </div>
  )
}

function ColumnSelect({
  value,
  onChange,
  dataset,
  label,
  allowNone,
}: {
  value: string | null | undefined
  onChange: (v: string | null) => void
  dataset?: DatasetInfo
  label: string
  allowNone?: boolean
}) {
  return (
    <Field label={label}>
      <Select
        value={value || NONE}
        onValueChange={(v) => onChange(v === NONE ? null : v)}
      >
        <SelectTrigger size='sm' className='h-8' aria-label={label}>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {allowNone ? <SelectItem value={NONE}>–</SelectItem> : null}
          {(dataset?.columns ?? []).map((c) => (
            <SelectItem key={c.key} value={c.key}>
              {c.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </Field>
  )
}

function ColumnChecks({
  dataset,
  picked,
  onChange,
  only,
}: {
  dataset?: DatasetInfo
  picked: string[]
  onChange: (keys: string[]) => void
  only?: (c: DatasetInfo['columns'][number]) => boolean
}) {
  return (
    <div className='flex flex-wrap gap-x-3 gap-y-1'>
      {(dataset?.columns ?? []).filter(only ?? (() => true)).map((c) => (
        <label key={c.key} className='flex items-center gap-1 text-xs'>
          <Checkbox
            checked={picked.includes(c.key)}
            onCheckedChange={(on) =>
              onChange(
                on ? [...picked, c.key] : picked.filter((k) => k !== c.key)
              )
            }
          />
          {c.label}
        </label>
      ))}
    </div>
  )
}

function FiltersField({
  value,
  onChange,
}: {
  value: Record<string, unknown>
  onChange: (v: Record<string, unknown>) => void
}) {
  const { t } = useTranslation()
  const [text, setText] = useState(
    Object.keys(value).length ? JSON.stringify(value) : ''
  )
  return (
    <Field label={t('reporting.filters_json')}>
      <Input
        className='h-8 font-mono text-xs'
        placeholder='{"status": ["todo", "review"]}'
        value={text}
        onChange={(e) => setText(e.target.value)}
        onBlur={() => {
          if (!text.trim()) return onChange({})
          try {
            const parsed = JSON.parse(text)
            if (parsed && typeof parsed === 'object' && !Array.isArray(parsed))
              onChange(parsed)
            else throw new Error()
          } catch {
            toast.error(t('reporting.bad_filters'))
          }
        }}
      />
    </Field>
  )
}

function SectionEditor({
  section,
  onChange,
  datasets,
}: {
  section: Section
  onChange: (s: Section) => void
  datasets: DatasetInfo[]
}) {
  const { t } = useTranslation()
  const { data: kpis = [] } = useKpiDefinitions()
  const title = (
    <Field label={t('reporting.section_title')}>
      <Input
        className='h-8'
        value={section.title ?? ''}
        onChange={(e) => onChange({ ...section, title: e.target.value })}
      />
    </Field>
  )
  if (section.type === 'text')
    return (
      <div className='grid gap-2'>
        {title}
        <Textarea
          rows={4}
          value={section.body ?? ''}
          onChange={(e) => onChange({ ...section, body: e.target.value })}
        />
      </div>
    )
  if (section.type === 'kpis')
    return (
      <div className='grid gap-2'>
        {title}
        <p className='text-xs text-muted-foreground'>
          {t('reporting.kpis_hint')}
        </p>
        <div className='flex flex-wrap gap-x-3 gap-y-1'>
          {kpis.map((k) => (
            <label key={k.key} className='flex items-center gap-1 text-xs'>
              <Checkbox
                checked={(section.keys ?? []).includes(k.key)}
                onCheckedChange={(on) =>
                  onChange({
                    ...section,
                    keys: on
                      ? [...(section.keys ?? []), k.key]
                      : (section.keys ?? []).filter((x) => x !== k.key),
                  })
                }
              />
              {k.label}
            </label>
          ))}
        </div>
      </div>
    )
  const dataset = datasets.find((d) => d.name === section.dataset)
  const datasetPicker = (
    <Field label={t('reporting.dataset')}>
      <Select
        value={section.dataset}
        onValueChange={(v) =>
          onChange({
            ...blank(section.type, v),
            title: section.title,
          } as Section)
        }
      >
        <SelectTrigger
          size='sm'
          className='h-8'
          aria-label={t('reporting.dataset')}
        >
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
    </Field>
  )
  if (section.type === 'table')
    return (
      <div className='grid gap-2'>
        <div className='grid gap-2 md:grid-cols-2'>
          {title}
          {datasetPicker}
        </div>
        <Field label={t('reporting.columns_pick')}>
          <ColumnChecks
            dataset={dataset}
            picked={section.columns ?? []}
            onChange={(columns) => onChange({ ...section, columns })}
          />
        </Field>
        <div className='grid gap-2 md:grid-cols-4'>
          <ColumnSelect
            label={t('reporting.group_by')}
            dataset={dataset}
            value={section.group_by}
            onChange={(group_by) => onChange({ ...section, group_by })}
            allowNone
          />
          <ColumnSelect
            label={t('reporting.sort_by')}
            dataset={dataset}
            value={section.sort_by}
            onChange={(sort_by) => onChange({ ...section, sort_by })}
            allowNone
          />
          <Field label={t('reporting.limit')}>
            <Input
              type='number'
              className='h-8'
              min={1}
              max={5000}
              value={section.limit ?? 500}
              onChange={(e) =>
                onChange({ ...section, limit: Number(e.target.value) || 500 })
              }
            />
          </Field>
          <label className='flex items-end gap-2 pb-1 text-xs'>
            <Switch
              checked={!!section.descending}
              onCheckedChange={(descending) =>
                onChange({ ...section, descending })
              }
            />
            {t('reporting.descending')}
          </label>
        </div>
        <FiltersField
          value={section.filters ?? {}}
          onChange={(filters) => onChange({ ...section, filters })}
        />
      </div>
    )
  if (section.type === 'chart')
    return (
      <div className='grid gap-2'>
        <div className='grid gap-2 md:grid-cols-2'>
          {title}
          {datasetPicker}
        </div>
        <div className='grid gap-2 md:grid-cols-4'>
          <Field label={t('reporting.chart_type')}>
            <Select
              value={section.chart ?? 'bar'}
              onValueChange={(v) => onChange({ ...section, chart: v as 'bar' })}
            >
              <SelectTrigger size='sm' className='h-8'>
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
          </Field>
          <ColumnSelect
            label={t('reporting.x_axis')}
            dataset={dataset}
            value={section.x}
            onChange={(x) => onChange({ ...section, x: x ?? '' })}
          />
          <Field label={t('reporting.aggregate')}>
            <Select
              value={section.agg ?? 'sum'}
              onValueChange={(v) => onChange({ ...section, agg: v as Agg })}
            >
              <SelectTrigger size='sm' className='h-8'>
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
          </Field>
          <ColumnSelect
            label={t('reporting.colour_by')}
            dataset={dataset}
            value={section.group_by}
            onChange={(group_by) => onChange({ ...section, group_by })}
            allowNone
          />
        </div>
        <Field label={t('reporting.y_series')}>
          <ColumnChecks
            dataset={dataset}
            picked={section.y}
            onChange={(y) => onChange({ ...section, y })}
            only={(c) => c.aggregatable}
          />
        </Field>
        <FiltersField
          value={section.filters ?? {}}
          onChange={(filters) => onChange({ ...section, filters })}
        />
      </div>
    )
  // pivot
  const value = section.values?.[0] ?? { field: '*', agg: 'count' as Agg }
  return (
    <div className='grid gap-2'>
      <div className='grid gap-2 md:grid-cols-2'>
        {title}
        {datasetPicker}
      </div>
      <Field label={t('reporting.rows')}>
        <ColumnChecks
          dataset={dataset}
          picked={section.rows ?? []}
          onChange={(rows) => onChange({ ...section, rows: rows.slice(0, 4) })}
        />
      </Field>
      <div className='grid gap-2 md:grid-cols-3'>
        <ColumnSelect
          label={t('reporting.columns')}
          dataset={dataset}
          value={section.columns?.[0]}
          onChange={(c) => onChange({ ...section, columns: c ? [c] : [] })}
          allowNone
        />
        <Field label={t('reporting.values')}>
          <Select
            value={value.field ?? '*'}
            onValueChange={(field) =>
              onChange({
                ...section,
                values: [
                  {
                    field,
                    agg: field === '*' ? 'count' : (value.agg ?? 'sum'),
                  },
                ],
              })
            }
          >
            <SelectTrigger size='sm' className='h-8'>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value='*'>Rows (count)</SelectItem>
              {(dataset?.columns ?? []).map((c) => (
                <SelectItem key={c.key} value={c.key}>
                  {c.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Field>
        <Field label={t('reporting.aggregate')}>
          <Select
            value={value.agg ?? 'count'}
            onValueChange={(agg) =>
              onChange({ ...section, values: [{ ...value, agg: agg as Agg }] })
            }
          >
            <SelectTrigger size='sm' className='h-8'>
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
        </Field>
      </div>
      <FiltersField
        value={section.filters ?? {}}
        onChange={(filters) => onChange({ ...section, filters })}
      />
    </div>
  )
}

export function TemplateEditor({
  template,
  onDone,
}: {
  template: Template | null
  onDone: () => void
}) {
  const { t } = useTranslation()
  const { data: datasets = [] } = useDatasets()
  const save = useSaveTemplate()
  const [draft, setDraft] = useState<TemplateIn>(() => ({
    name: template?.name ?? '',
    description: template?.description ?? null,
    sections: template?.sections ?? [],
    branding: template?.branding ?? { company_name: null, logo_file_id: null },
    landscape: template?.landscape ?? false,
  }))
  const [dragging, setDragging] = useState<number | null>(null)
  const [overIndex, setOverIndex] = useState<number | null>(null)
  const sections = draft.sections ?? []
  const setSections = (next: Section[]) =>
    setDraft({ ...draft, sections: next })
  const firstDataset = datasets[0]?.name ?? 'projects'

  const insert = (kind: Kind, at = sections.length) =>
    setSections([
      ...sections.slice(0, at),
      blank(kind, firstDataset),
      ...sections.slice(at),
    ])
  const move = (from: number, to: number) => {
    if (to < 0 || to >= sections.length || from === to) return
    const next = [...sections]
    const [item] = next.splice(from, 1)
    next.splice(to, 0, item)
    setSections(next)
  }

  const uploadLogo = async (file: File) => {
    const form = new FormData()
    form.set('file', file)
    form.set('category', 'other')
    try {
      const stored = await uploadFile(form)
      setDraft({
        ...draft,
        branding: { ...draft.branding, logo_file_id: stored.id },
      })
      toast.success(t('reporting.logo_uploaded'))
    } catch {
      toast.error(t('reporting.logo_failed'))
    }
  }

  return (
    <div className='flex flex-col gap-4'>
      <div className='grid gap-3 md:grid-cols-2'>
        <Field label={t('reporting.template_name')}>
          <Input
            value={draft.name}
            onChange={(e) => setDraft({ ...draft, name: e.target.value })}
          />
        </Field>
        <Field label={t('reporting.description')}>
          <Input
            value={draft.description ?? ''}
            onChange={(e) =>
              setDraft({ ...draft, description: e.target.value || null })
            }
          />
        </Field>
        <Field label={t('reporting.company_name')}>
          <Input
            value={draft.branding?.company_name ?? ''}
            onChange={(e) =>
              setDraft({
                ...draft,
                branding: {
                  ...draft.branding,
                  company_name: e.target.value || null,
                },
              })
            }
          />
        </Field>
        <Field label={t('reporting.logo')}>
          <div className='flex items-center gap-2'>
            <Input
              type='file'
              accept='image/png,image/jpeg'
              className='h-9'
              onChange={(e) => {
                const file = e.target.files?.[0]
                if (file) void uploadLogo(file)
              }}
            />
            {draft.branding?.logo_file_id ? (
              <span className='text-xs text-muted-foreground'>
                #{draft.branding.logo_file_id}
              </span>
            ) : null}
          </div>
        </Field>
        <label className='flex items-center gap-2 text-sm'>
          <Switch
            checked={!!draft.landscape}
            onCheckedChange={(landscape) => setDraft({ ...draft, landscape })}
          />
          {t('reporting.landscape')}
        </label>
      </div>

      <div className='flex flex-wrap items-center gap-2'>
        <span className='text-xs font-semibold text-muted-foreground uppercase'>
          {t('reporting.add_section')}
        </span>
        {PALETTE.map(({ kind, icon: Icon }) => (
          <Button
            key={kind}
            size='sm'
            variant='outline'
            draggable
            onDragStart={(e) =>
              e.dataTransfer.setData('application/x-section', kind)
            }
            onClick={() => insert(kind)}
          >
            <Icon /> {t(`reporting.section_${kind}`)}
          </Button>
        ))}
      </div>

      <div
        className='flex flex-col gap-3'
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => {
          const kind = e.dataTransfer.getData('application/x-section') as Kind
          if (kind) insert(kind, overIndex ?? sections.length)
          else if (dragging !== null && overIndex !== null)
            move(dragging, overIndex)
          setDragging(null)
          setOverIndex(null)
        }}
      >
        {sections.length === 0 ? (
          <p className='rounded-md border border-dashed p-6 text-center text-sm text-muted-foreground'>
            {t('reporting.no_sections')}
          </p>
        ) : null}
        {sections.map((section, i) => (
          <Card
            key={i}
            data-testid='section'
            onDragOver={() => setOverIndex(i)}
            className={cn(
              'gap-2 py-3',
              overIndex === i && dragging !== i && 'ring-2 ring-primary'
            )}
          >
            <CardHeader className='flex flex-row items-center gap-2 px-4'>
              <span
                draggable
                onDragStart={() => setDragging(i)}
                className='cursor-grab text-muted-foreground'
                aria-label={t('reporting.drag_section')}
              >
                <GripVertical className='size-4' />
              </span>
              <span className='text-sm font-medium'>
                {t(`reporting.section_${section.type}`)}
              </span>
              <div className='ms-auto flex gap-1'>
                <Button
                  size='icon'
                  variant='ghost'
                  className='size-7'
                  aria-label={t('reporting.move_up')}
                  onClick={() => move(i, i - 1)}
                >
                  <ArrowUp />
                </Button>
                <Button
                  size='icon'
                  variant='ghost'
                  className='size-7'
                  aria-label={t('reporting.move_down')}
                  onClick={() => move(i, i + 1)}
                >
                  <ArrowDown />
                </Button>
                <Button
                  size='icon'
                  variant='ghost'
                  className='size-7 hover:text-red-600'
                  aria-label={t('reporting.remove_section')}
                  onClick={() =>
                    setSections(sections.filter((_, j) => j !== i))
                  }
                >
                  <Trash2 />
                </Button>
              </div>
            </CardHeader>
            <CardContent className='px-4'>
              <SectionEditor
                section={section}
                datasets={datasets}
                onChange={(s) =>
                  setSections(sections.map((x, j) => (j === i ? s : x)))
                }
              />
            </CardContent>
          </Card>
        ))}
      </div>

      <div className='flex justify-end gap-2'>
        <Button variant='outline' onClick={onDone}>
          {t('common.cancel')}
        </Button>
        <Button
          disabled={!draft.name.trim() || save.isPending}
          onClick={() =>
            save.mutate(
              {
                id: template?.builtin_key ? undefined : template?.id,
                body: draft,
              },
              { onSuccess: onDone }
            )
          }
        >
          <Plus /> {t('common.save')}
        </Button>
      </div>
    </div>
  )
}
