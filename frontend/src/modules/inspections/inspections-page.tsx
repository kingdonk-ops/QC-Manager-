import { useMemo, useState } from 'react'
import { Link, useNavigate } from '@tanstack/react-router'
import type { ColDef, ICellRendererParams } from 'ag-grid-community'
import { ClipboardList, Plus } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useCurrentProject } from '@/stores/use-current-project'
import { can, useSession } from '@/lib/session'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { DataGrid } from '@/components/data-grid'
import { Page } from '@/components/layout/page'
import { NativeSelect, UserSelect } from '@/components/native-select'
import { StatusBadge } from '@/components/records/status-badge'
import {
  type Inspection,
  STATUSES,
  useCreateInspection,
  useInspections,
  useTemplates,
  useTrends,
} from './api'
import { TrendChart } from './trend-chart'

export function PassRate({ value }: { value?: number | null }) {
  if (value === null || value === undefined)
    return <span className='text-muted-foreground'>—</span>
  const tone =
    value >= 90
      ? 'text-green-600'
      : value >= 70
        ? 'text-amber-600'
        : 'text-red-600'
  return <span className={`font-medium tabular-nums ${tone}`}>{value}%</span>
}

function NewInspection({
  projectId,
  open,
  onClose,
}: {
  projectId: number
  open: boolean
  onClose: () => void
}) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const session = useSession()
  const { data: templates = [] } = useTemplates(projectId)
  const create = useCreateInspection()
  const [draft, setDraft] = useState({
    template_id: '',
    location: '',
    area: '',
    scheduled_date: '',
    inspector_id: session.id as number | null,
  })

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('inspections.new')}</DialogTitle>
        </DialogHeader>
        <form
          id='new-inspection'
          className='grid gap-3'
          onSubmit={(e) => {
            e.preventDefault()
            create.mutate(
              {
                project_id: projectId,
                template_id: Number(draft.template_id),
                location: draft.location || null,
                area: draft.area || null,
                scheduled_date: draft.scheduled_date || null,
                inspector_id: draft.inspector_id,
              },
              {
                onSuccess: (made) => {
                  onClose()
                  void navigate({ to: `/inspections/${made.id}` as never })
                },
              }
            )
          }}
        >
          <div className='grid gap-1.5'>
            <Label htmlFor='ins-template'>{t('inspections.template')}</Label>
            <NativeSelect
              id='ins-template'
              required
              placeholder={t('inspections.choose_template')}
              options={templates.map((tpl) => ({
                value: String(tpl.id),
                label: `${tpl.name}${tpl.trade ? ` · ${tpl.trade}` : ''} (v${tpl.version})`,
              }))}
              value={draft.template_id}
              onChange={(e) =>
                setDraft({ ...draft, template_id: e.target.value })
              }
            />
          </div>
          <div className='grid grid-cols-2 gap-3'>
            <div className='grid gap-1.5'>
              <Label htmlFor='ins-location'>{t('inspections.location')}</Label>
              <Input
                id='ins-location'
                value={draft.location}
                placeholder='Pipe rack 3'
                onChange={(e) =>
                  setDraft({ ...draft, location: e.target.value })
                }
              />
            </div>
            <div className='grid gap-1.5'>
              <Label htmlFor='ins-area'>{t('inspections.area')}</Label>
              <Input
                id='ins-area'
                value={draft.area}
                placeholder='Level 2, line 12'
                onChange={(e) => setDraft({ ...draft, area: e.target.value })}
              />
            </div>
            <div className='grid gap-1.5'>
              <Label htmlFor='ins-inspector'>
                {t('inspections.inspector')}
              </Label>
              <UserSelect
                id='ins-inspector'
                value={draft.inspector_id}
                onChange={(id) => setDraft({ ...draft, inspector_id: id })}
              />
            </div>
            <div className='grid gap-1.5'>
              <Label htmlFor='ins-date'>{t('inspections.scheduled')}</Label>
              <Input
                id='ins-date'
                type='date'
                value={draft.scheduled_date}
                onChange={(e) =>
                  setDraft({ ...draft, scheduled_date: e.target.value })
                }
              />
            </div>
          </div>
        </form>
        <DialogFooter>
          <Button
            type='submit'
            form='new-inspection'
            disabled={create.isPending || !draft.template_id}
          >
            {t('inspections.start')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function Register({ projectId }: { projectId: number }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const session = useSession()
  const [status, setStatus] = useState('')
  const [groupBy, setGroupBy] = useState<'trade' | 'location'>('trade')
  const [creating, setCreating] = useState(false)
  const { data: rows = [] } = useInspections(projectId, status)
  const { data: trends } = useTrends(projectId, groupBy)

  const columns = useMemo<ColDef<Inspection>[]>(
    () => [
      {
        field: 'code',
        headerName: t('inspections.code'),
        width: 100,
        cellClass: 'font-mono',
      },
      {
        field: 'title',
        headerName: t('inspections.title_col'),
        flex: 1,
        minWidth: 200,
      },
      { field: 'location', headerName: t('inspections.location'), width: 150 },
      { field: 'area', headerName: t('inspections.area'), width: 130 },
      { field: 'trade', headerName: t('inspections.trade'), width: 120 },
      {
        field: 'inspector_name',
        headerName: t('inspections.inspector'),
        width: 150,
      },
      {
        field: 'scheduled_date',
        headerName: t('inspections.scheduled'),
        width: 120,
      },
      {
        field: 'inspected_date',
        headerName: t('inspections.inspected'),
        width: 120,
      },
      {
        field: 'status',
        headerName: t('inspections.status'),
        width: 130,
        cellRenderer: (p: ICellRendererParams<Inspection>) => (
          <StatusBadge status={p.value} />
        ),
      },
      {
        field: 'pass_rate',
        headerName: t('inspections.score'),
        width: 100,
        type: 'rightAligned',
        cellRenderer: (p: ICellRendererParams<Inspection>) => (
          <PassRate value={p.value} />
        ),
      },
      {
        headerName: t('inspections.failed'),
        field: 'failed',
        width: 90,
        type: 'rightAligned',
        cellClass: (p) => (p.value ? 'text-red-600 font-medium' : ''),
      },
    ],
    [t]
  )

  return (
    <>
      <div className='flex flex-wrap items-center gap-2'>
        <NativeSelect
          className='h-8 w-44'
          aria-label={t('inspections.status')}
          placeholder={t('inspections.all_statuses')}
          values={STATUSES}
          value={status}
          onChange={(e) => setStatus(e.target.value)}
        />
        <div className='ms-auto flex gap-2'>
          <Button size='sm' variant='outline' asChild>
            <Link to='/$' params={{ _splat: 'inspections/templates' }}>
              <ClipboardList /> {t('inspections.templates')}
            </Link>
          </Button>
          {can(session, 'inspections.create') ? (
            <Button size='sm' onClick={() => setCreating(true)}>
              <Plus /> {t('inspections.new')}
            </Button>
          ) : null}
        </div>
      </div>
      <div className='h-[420px]'>
        <DataGrid<Inspection>
          rowData={rows}
          columnDefs={columns}
          getRowId={(p) => String(p.data.id)}
          rowClass='cursor-pointer'
          onRowClicked={(e) =>
            e.data &&
            void navigate({ to: `/inspections/${e.data.id}` as never })
          }
        />
      </div>
      <Card>
        <CardHeader className='flex flex-row items-center justify-between'>
          <CardTitle className='text-base'>{t('inspections.trends')}</CardTitle>
          <NativeSelect
            className='h-8 w-40'
            aria-label={t('inspections.group_by')}
            options={[
              { value: 'trade', label: t('inspections.by_trade') },
              { value: 'location', label: t('inspections.by_location') },
            ]}
            value={groupBy}
            onChange={(e) => setGroupBy(e.target.value as 'trade' | 'location')}
          />
        </CardHeader>
        <CardContent className='grid gap-4'>
          <TrendChart trends={trends} />
          {trends?.groups.length ? (
            <div className='flex flex-wrap gap-2'>
              {trends.groups.map((g) => (
                <div
                  key={g.key}
                  className='rounded-md border px-3 py-1.5 text-sm'
                >
                  <span className='font-medium'>{g.key}</span>{' '}
                  <PassRate value={g.pass_rate} />{' '}
                  <span className='text-xs text-muted-foreground'>
                    {g.inspections} {t('inspections.inspections')}
                  </span>
                </div>
              ))}
            </div>
          ) : null}
        </CardContent>
      </Card>
      {creating ? (
        <NewInspection
          projectId={projectId}
          open
          onClose={() => setCreating(false)}
        />
      ) : null}
    </>
  )
}

export default function InspectionsPage() {
  const { t } = useTranslation()
  const project = useCurrentProject()
  return (
    <Page
      title={t('inspections.page_title')}
      description={t('inspections.description')}
      projectScoped
    >
      {project ? (
        <Register key={project.id} projectId={project.id} />
      ) : (
        <p className='text-sm text-muted-foreground'>
          {t('inspections.no_project')}
        </p>
      )}
    </Page>
  )
}
