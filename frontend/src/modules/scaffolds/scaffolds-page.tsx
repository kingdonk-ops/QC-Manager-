import { useMemo, useState } from 'react'
import type { ColDef, ICellRendererParams } from 'ag-grid-community'
import { CloudLightning, Download, Plus } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useCurrentProject } from '@/stores/use-current-project'
import { can, useSession } from '@/lib/session'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { DataGrid } from '@/components/data-grid'
import { Page } from '@/components/layout/page'
import { NativeSelect } from '@/components/native-select'
import { StatusBadge } from '@/components/records/status-badge'
import {
  STATUSES,
  type Scaffold,
  TAGS,
  useScaffolds,
  useTagBoard,
} from './api'
import { HireView } from './hire-panel'
import { ScaffoldSheet, TagPill } from './scaffold-sheet'
import { RequestScaffold, Weather } from './scaffolds-dialogs'

function initialId() {
  const id = Number(new URLSearchParams(window.location.search).get('id'))
  return Number.isFinite(id) && id > 0 ? id : null
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
