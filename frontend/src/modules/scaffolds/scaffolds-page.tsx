import { useMemo, useState } from 'react'
import type { ColDef, ICellRendererParams } from 'ag-grid-community'
import { CloudLightning, Download, Plus } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useCurrentProject } from '@/stores/use-current-project'
import { money } from '@/lib/format'
import { can, useSession } from '@/lib/session'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Textarea } from '@/components/ui/textarea'
import { DataGrid } from '@/components/data-grid'
import { Page } from '@/components/layout/page'
import { NativeSelect, UserSelect } from '@/components/native-select'
import { NodeSelect } from '@/components/node-select'
import { Field } from '@/components/records/fields'
import { StatusBadge } from '@/components/records/status-badge'
import {
  DUTIES,
  STATUSES,
  type Scaffold,
  TAGS,
  TYPES,
  useCreateScaffold,
  useHire,
  useScaffolds,
  useTagBoard,
  useWeatherEvent,
} from './api'
import { ScaffoldSheet, TagPill } from './scaffold-sheet'

function initialId() {
  const id = Number(new URLSearchParams(window.location.search).get('id'))
  return Number.isFinite(id) && id > 0 ? id : null
}

function RequestScaffold({
  projectId,
  onClose,
  onCreated,
}: {
  projectId: number
  onClose: () => void
  onCreated: (id: number) => void
}) {
  const { t } = useTranslation()
  const create = useCreateScaffold()
  const [nodeId, setNodeId] = useState<number | null>(null)
  const [custodian, setCustodian] = useState<number | null>(null)
  const [draft, setDraft] = useState({
    purpose: '',
    location_text: '',
    scaffold_type: 'independent',
    duty_class: 'medium',
    required_by: '',
    length_m: '',
    width_m: '',
    height_m: '',
    lifts: '',
  })
  const text = (key: keyof typeof draft) => ({
    value: draft[key],
    onChange: (
      e: React.ChangeEvent<
        HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement
      >
    ) => setDraft({ ...draft, [key]: e.target.value }),
  })
  const num = (v: string) => (v ? Number(v) : null)
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className='sm:max-w-lg'>
        <DialogHeader>
          <DialogTitle>{t('scaffolds.request')}</DialogTitle>
        </DialogHeader>
        <form
          id='new-scaffold'
          className='grid gap-3'
          onSubmit={(e) => {
            e.preventDefault()
            if (!nodeId) return
            create.mutate(
              {
                project_id: projectId,
                node_id: nodeId,
                purpose: draft.purpose || null,
                location_text: draft.location_text || null,
                scaffold_type: draft.scaffold_type as never,
                duty_class: draft.duty_class as never,
                required_by: draft.required_by || null,
                custodian_id: custodian,
                dimensions: {
                  length_m: num(draft.length_m),
                  width_m: num(draft.width_m),
                  height_m: num(draft.height_m),
                  lifts: num(draft.lifts),
                },
              },
              {
                onSuccess: (made) => {
                  onClose()
                  onCreated(made.id)
                },
              }
            )
          }}
        >
          <Field label={t('scaffolds.location')}>
            <NodeSelect
              projectId={projectId}
              value={nodeId}
              onChange={setNodeId}
            />
          </Field>
          <Field label={t('scaffolds.location_detail')}>
            <Input {...text('location_text')} />
          </Field>
          <Field label={t('scaffolds.purpose')}>
            <Textarea {...text('purpose')} />
          </Field>
          <div className='grid grid-cols-2 gap-3'>
            <Field label={t('scaffolds.type')}>
              <NativeSelect values={TYPES} {...text('scaffold_type')} />
            </Field>
            <Field label={t('scaffolds.duty')}>
              <NativeSelect values={DUTIES} {...text('duty_class')} />
            </Field>
            <Field label={t('scaffolds.required_by')}>
              <Input type='date' {...text('required_by')} />
            </Field>
            <Field label={t('scaffolds.custodian')}>
              <UserSelect value={custodian} onChange={setCustodian} />
            </Field>
          </div>
          <div className='grid grid-cols-4 gap-2'>
            <Field label='L (m)'>
              <Input type='number' step='0.1' {...text('length_m')} />
            </Field>
            <Field label='W (m)'>
              <Input type='number' step='0.1' {...text('width_m')} />
            </Field>
            <Field label='H (m)'>
              <Input type='number' step='0.1' {...text('height_m')} />
            </Field>
            <Field label={t('scaffolds.lifts')}>
              <Input type='number' {...text('lifts')} />
            </Field>
          </div>
        </form>
        <DialogFooter>
          <Button
            type='submit'
            form='new-scaffold'
            disabled={!nodeId || create.isPending}
          >
            {t('scaffolds.request')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function Weather({
  projectId,
  onClose,
}: {
  projectId: number
  onClose: () => void
}) {
  const { t } = useTranslation()
  const weather = useWeatherEvent()
  const [nodeId, setNodeId] = useState<number | null>(null)
  const [description, setDescription] = useState('')
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className='sm:max-w-md'>
        <DialogHeader>
          <DialogTitle>{t('scaffolds.weather_event')}</DialogTitle>
        </DialogHeader>
        <p className='text-sm text-muted-foreground'>
          {t('scaffolds.weather_help')}
        </p>
        <Field label={t('scaffolds.area_optional')}>
          <NodeSelect
            projectId={projectId}
            value={nodeId}
            onChange={setNodeId}
          />
        </Field>
        <Field label={t('scaffolds.what_happened')}>
          <Textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
        </Field>
        <DialogFooter>
          <Button
            disabled={!description || weather.isPending}
            onClick={() =>
              weather.mutate(
                {
                  project_id: projectId,
                  node_id: nodeId ?? undefined,
                  description,
                },
                { onSuccess: onClose }
              )
            }
          >
            {t('scaffolds.record')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function Register({
  projectId,
  onOpen,
}: {
  projectId: number
  onOpen: (id: number) => void
}) {
  const { t } = useTranslation()
  const [filters, setFilters] = useState({
    status: '',
    tag: '',
    search: '',
    active_only: true,
  })
  const { data: rows = [] } = useScaffolds(projectId, filters)
  const columns = useMemo<ColDef<Scaffold>[]>(
    () => [
      { field: 'code', headerName: t('scaffolds.code'), width: 100 },
      { field: 'tag_no', headerName: t('scaffolds.tag_no'), width: 100 },
      {
        field: 'effective_tag',
        headerName: t('scaffolds.tag'),
        width: 110,
        cellRenderer: (p: ICellRendererParams<Scaffold>) => (
          <TagPill tag={p.value} />
        ),
      },
      {
        field: 'status',
        headerName: t('scaffolds.status'),
        width: 170,
        cellRenderer: (p: ICellRendererParams<Scaffold>) => (
          <StatusBadge status={p.value} />
        ),
      },
      {
        field: 'node_path',
        headerName: t('scaffolds.location'),
        flex: 1,
        minWidth: 200,
      },
      { field: 'scaffold_type', headerName: t('scaffolds.type'), width: 120 },
      {
        field: 'required_by',
        headerName: t('scaffolds.required_by'),
        width: 120,
      },
      {
        field: 'next_inspection_due',
        headerName: t('scaffolds.next_due'),
        width: 150,
        valueFormatter: (p) =>
          p.value ? new Date(p.value).toLocaleDateString() : '',
        cellClass: (p) =>
          p.data?.inspection_overdue ? 'font-semibold text-red-600' : '',
      },
      {
        field: 'days_erected',
        headerName: t('scaffolds.days_erected'),
        width: 110,
        type: 'rightAligned',
      },
    ],
    [t]
  )
  return (
    <div className='grid gap-3'>
      <div className='flex flex-wrap items-center gap-2'>
        <Input
          className='h-8 w-56'
          placeholder={t('scaffolds.search')}
          value={filters.search}
          onChange={(e) => setFilters({ ...filters, search: e.target.value })}
        />
        <NativeSelect
          className='h-8 w-48'
          aria-label={t('scaffolds.status')}
          placeholder={t('scaffolds.all_statuses')}
          values={STATUSES}
          value={filters.status}
          onChange={(e) => setFilters({ ...filters, status: e.target.value })}
        />
        <NativeSelect
          className='h-8 w-36'
          aria-label={t('scaffolds.tag')}
          placeholder={t('scaffolds.all_tags')}
          values={[...TAGS, 'none']}
          value={filters.tag}
          onChange={(e) => setFilters({ ...filters, tag: e.target.value })}
        />
        <label className='flex items-center gap-1.5 text-sm'>
          <input
            type='checkbox'
            checked={filters.active_only}
            onChange={(e) =>
              setFilters({ ...filters, active_only: e.target.checked })
            }
          />
          {t('scaffolds.active_only')}
        </label>
      </div>
      <div className='h-[560px]'>
        <DataGrid<Scaffold>
          rowData={rows}
          columnDefs={columns}
          getRowId={(p) => String(p.data.id)}
          rowClass='cursor-pointer'
          onRowClicked={(e) => e.data && onOpen(e.data.id)}
        />
      </div>
    </div>
  )
}

function Board({
  projectId,
  onOpen,
}: {
  projectId: number
  onOpen: (id: number) => void
}) {
  const { t } = useTranslation()
  const { data } = useTagBoard(projectId)
  const columns = ['green', 'yellow', 'red', 'none'] as const
  return (
    <div className='grid gap-3 md:grid-cols-4'>
      {columns.map((tag) => (
        <section key={tag} className='grid content-start gap-2'>
          <h3 className='flex items-center gap-2 text-sm font-semibold'>
            <TagPill tag={tag} /> {data?.[tag].length ?? 0}
          </h3>
          {(data?.[tag] ?? []).map((s) => (
            <button
              key={s.id}
              type='button'
              onClick={() => onOpen(s.id)}
              className='rounded-md border p-2 text-start text-sm hover:bg-muted'
            >
              <div className='flex justify-between font-medium'>
                <span>{s.code}</span>
                <span className='font-mono text-xs'>{s.tag_no}</span>
              </div>
              <div className='text-xs text-muted-foreground'>{s.node_path}</div>
              <div className='text-xs'>
                {s.inspection_overdue
                  ? t('scaffolds.overdue')
                  : s.next_inspection_due
                    ? `${t('scaffolds.next_due')} ${new Date(s.next_inspection_due).toLocaleDateString()}`
                    : t('scaffolds.awaiting_handover')}
              </div>
            </button>
          ))}
        </section>
      ))}
    </div>
  )
}

function HireView({
  projectId,
  currency,
}: {
  projectId: number
  currency: string
}) {
  const { t } = useTranslation()
  const [start, setStart] = useState('')
  const { data } = useHire(projectId, start)
  const fmt = money(currency)
  return (
    <div className='grid gap-3'>
      <div className='flex items-end gap-2'>
        <Field label={t('scaffolds.period_from')}>
          <Input
            type='date'
            className='h-8 w-44'
            value={start}
            onChange={(e) => setStart(e.target.value)}
          />
        </Field>
        <p className='pb-1 text-sm text-muted-foreground'>
          {t('scaffolds.hire_help')}
        </p>
      </div>
      <table className='w-full text-sm'>
        <thead className='text-left text-muted-foreground'>
          <tr>
            <th>{t('scaffolds.code')}</th>
            <th>{t('scaffolds.location')}</th>
            <th>{t('scaffolds.erected')}</th>
            <th className='text-right'>{t('scaffolds.days')}</th>
            <th className='text-right'>{t('scaffolds.hire_rate')}</th>
            <th className='text-right'>{t('scaffolds.hire_cost')}</th>
          </tr>
        </thead>
        <tbody>
          {(data?.lines ?? []).map((l) => (
            <tr key={l.scaffold_id} className='border-t'>
              <td>{l.code}</td>
              <td>{l.node_path}</td>
              <td>
                {l.erected_on}
                {l.dismantled_on ? ` → ${l.dismantled_on}` : ''}
              </td>
              <td className='text-right'>{l.days}</td>
              <td className='text-right'>
                {l.rate != null ? fmt({ value: l.rate }) : '—'}
              </td>
              <td className='text-right'>
                {l.cost != null ? fmt({ value: l.cost }) : '—'}
              </td>
            </tr>
          ))}
          <tr className='border-t font-semibold'>
            <td colSpan={3}>{t('scaffolds.total')}</td>
            <td className='text-right'>{data?.total_days ?? 0}</td>
            <td />
            <td className='text-right'>
              {fmt({ value: data?.total_cost ?? 0 })}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  )
}

export default function ScaffoldsPage() {
  const { t } = useTranslation()
  const session = useSession()
  const project = useCurrentProject()
  const [openId, setOpenId] = useState<number | null>(initialId)
  const [requesting, setRequesting] = useState(false)
  const [weather, setWeather] = useState(false)
  return (
    <Page
      title={t('scaffolds.title')}
      description={t('scaffolds.description')}
      projectScoped
      actions={
        project ? (
          <>
            {can(session, 'scaffolds.export') ? (
              <Button size='sm' variant='outline' asChild>
                <a
                  href={`/api/v1/scaffolds/export?project_id=${project.id}&format=xlsx`}
                >
                  <Download /> {t('scaffolds.export')}
                </a>
              </Button>
            ) : null}
            {can(session, 'scaffolds.update') ? (
              <Button
                size='sm'
                variant='outline'
                onClick={() => setWeather(true)}
              >
                <CloudLightning /> {t('scaffolds.weather_event')}
              </Button>
            ) : null}
            {can(session, 'scaffolds.create') ? (
              <Button size='sm' onClick={() => setRequesting(true)}>
                <Plus /> {t('scaffolds.request')}
              </Button>
            ) : null}
          </>
        ) : null
      }
    >
      {project ? (
        <Tabs defaultValue='register' key={project.id}>
          <TabsList>
            <TabsTrigger value='register'>
              {t('scaffolds.register')}
            </TabsTrigger>
            <TabsTrigger value='board'>{t('scaffolds.tag_board')}</TabsTrigger>
            <TabsTrigger value='hire'>{t('scaffolds.hire')}</TabsTrigger>
          </TabsList>
          <TabsContent value='register'>
            <Register projectId={project.id} onOpen={setOpenId} />
          </TabsContent>
          <TabsContent value='board'>
            <Board projectId={project.id} onOpen={setOpenId} />
          </TabsContent>
          <TabsContent value='hire'>
            <HireView projectId={project.id} currency={project.currency} />
          </TabsContent>
          {requesting ? (
            <RequestScaffold
              projectId={project.id}
              onClose={() => setRequesting(false)}
              onCreated={setOpenId}
            />
          ) : null}
          {weather ? (
            <Weather projectId={project.id} onClose={() => setWeather(false)} />
          ) : null}
        </Tabs>
      ) : (
        <p className='text-sm text-muted-foreground'>
          {t('scaffolds.no_project')}
        </p>
      )}
      <ScaffoldSheet id={openId} onClose={() => setOpenId(null)} />
    </Page>
  )
}
