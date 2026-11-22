import { useMemo, useState } from 'react'
import type { ColDef } from 'ag-grid-community'
import { Plus } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useCurrentProject } from '@/stores/use-current-project'
import { can, useSession } from '@/lib/session'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { DataGrid } from '@/components/data-grid'
import { Page } from '@/components/layout/page'
import { SelectField } from '@/components/records/fields'
import { StatusBadge } from '@/components/records/status-badge'
import { useDrawings, useWelds, WELD_STATUSES, type Weld } from './api'
import { JointsTab } from './joints-tab'
import { NdeTab } from './nde-tab'
import { WeldSheet } from './weld-sheet'
import { WeldersTab } from './welders-tab'

function initialId() {
  const id = Number(new URLSearchParams(window.location.search).get('id'))
  return Number.isFinite(id) && id > 0 ? id : undefined
}

/** The weld register, with the weld maps (one per drawing) on the left. */
function WeldsTab({ projectId }: { projectId: number }) {
  const { t } = useTranslation()
  const session = useSession()
  const [drawing, setDrawing] = useState<string>()
  const [status, setStatus] = useState<string>()
  const [search, setSearch] = useState('')
  const [openId, setOpenId] = useState<number | 'new' | undefined>(initialId)
  const { data: welds = [] } = useWelds(projectId, {
    drawing_ref: drawing,
    status,
    search,
  })
  const { data: drawings = [] } = useDrawings(projectId)
  const columns = useMemo<ColDef<Weld>[]>(
    () => [
      {
        field: 'weld_number',
        headerName: t('welding.weld_number'),
        width: 110,
        cellClass: 'font-mono',
        valueFormatter: (p) =>
          `${p.value}${p.data?.repair_label ? ` ${p.data.repair_label}` : ''}`,
      },
      { field: 'drawing_ref', headerName: t('welding.drawing'), width: 130 },
      { field: 'joint_type', headerName: t('welding.joint_type'), width: 90 },
      { field: 'diameter', headerName: 'Ø', width: 70 },
      { field: 'wps_code', headerName: t('welding.wps'), width: 120 },
      {
        field: 'welders',
        headerName: t('welding.welders'),
        width: 120,
        valueFormatter: (p) => (p.value as string[]).join(', '),
      },
      { field: 'welded_on', headerName: t('welding.welded_on'), width: 115 },
      {
        field: 'nde_summary',
        headerName: 'NDE',
        flex: 1,
        minWidth: 140,
        valueFormatter: (p) =>
          Object.entries((p.value ?? {}) as Record<string, string>)
            .map(([m, r]) => `${m.toUpperCase()} ${r}`)
            .join(', '),
      },
      {
        field: 'status',
        headerName: t('welding.status'),
        width: 130,
        cellRenderer: (p: { value?: string }) => (
          <StatusBadge status={p.value} />
        ),
      },
    ],
    [t]
  )
  return (
    <div className='grid gap-3 lg:grid-cols-[220px_minmax(0,1fr)]'>
      <nav className='grid content-start gap-1 text-sm'>
        <span className='text-xs font-medium text-muted-foreground'>
          {t('welding.weld_maps')}
        </span>
        <button
          className={cn(
            'rounded px-2 py-1 text-left hover:bg-muted',
            !drawing && 'bg-muted font-medium'
          )}
          onClick={() => setDrawing(undefined)}
        >
          {t('welding.all_drawings')}
        </button>
        {drawings.map((d) => (
          <button
            key={d.drawing_ref}
            className={cn(
              'flex justify-between rounded px-2 py-1 text-left hover:bg-muted',
              drawing === d.drawing_ref && 'bg-muted font-medium'
            )}
            onClick={() => setDrawing(d.drawing_ref)}
          >
            <span>{d.drawing_ref || '—'}</span>
            <span className='text-xs text-muted-foreground'>
              {d.accepted}/{d.welds}
              {d.rejected ? (
                <span className='text-red-600'> · {d.rejected}✗</span>
              ) : null}
            </span>
          </button>
        ))}
      </nav>
      <div className='grid gap-2'>
        <div className='flex flex-wrap items-center gap-2'>
          <Input
            className='h-8 w-56'
            placeholder={t('welding.search')}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <div className='w-44'>
            <SelectField
              value={status}
              onChange={(v) => setStatus(v ?? undefined)}
              options={WELD_STATUSES.map((s) => ({
                value: s,
                label: t(`welding.st.${s}`),
              }))}
              allowNone
              placeholder={t('welding.status')}
            />
          </div>
          {can(session, 'welding.create') ? (
            <Button
              size='sm'
              className='ms-auto'
              onClick={() => setOpenId('new')}
            >
              <Plus /> {t('welding.new_weld')}
            </Button>
          ) : null}
        </div>
        <div className='h-[520px]'>
          <DataGrid<Weld>
            rowData={welds}
            columnDefs={columns}
            getRowId={(p) => String(p.data.id)}
            rowClass='cursor-pointer'
            onRowClicked={(e) => e.data && setOpenId(e.data.id)}
          />
        </div>
      </div>
      {openId !== undefined ? (
        <WeldSheet
          key={openId}
          projectId={projectId}
          weldId={openId === 'new' ? undefined : openId}
          onClose={() => setOpenId(undefined)}
        />
      ) : null}
    </div>
  )
}

export default function WeldingPage() {
  const { t } = useTranslation()
  const project = useCurrentProject()
  return (
    <Page
      title={t('welding.title')}
      description={t('welding.description')}
      projectScoped
    >
      {project ? (
        <Tabs defaultValue='welds' key={project.id}>
          <TabsList>
            <TabsTrigger value='welds'>{t('welding.tab.welds')}</TabsTrigger>
            <TabsTrigger value='nde'>{t('welding.tab.nde')}</TabsTrigger>
            <TabsTrigger value='welders'>
              {t('welding.tab.welders')}
            </TabsTrigger>
            <TabsTrigger value='joints'>{t('welding.tab.joints')}</TabsTrigger>
          </TabsList>
          <TabsContent value='welds'>
            <WeldsTab projectId={project.id} />
          </TabsContent>
          <TabsContent value='nde'>
            <NdeTab projectId={project.id} />
          </TabsContent>
          <TabsContent value='welders'>
            <WeldersTab projectId={project.id} />
          </TabsContent>
          <TabsContent value='joints'>
            <JointsTab projectId={project.id} />
          </TabsContent>
        </Tabs>
      ) : (
        <p className='text-sm text-muted-foreground'>
          {t('welding.no_project')}
        </p>
      )}
    </Page>
  )
}
