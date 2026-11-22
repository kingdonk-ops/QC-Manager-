import { useMemo, useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import type { ColDef, ICellRendererParams } from 'ag-grid-community'
import { Download, Plus, Settings } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { api, unwrap } from '@/api/client'
import { useCurrentProject } from '@/stores/use-current-project'
import { handleServerError } from '@/lib/handle-server-error'
import { can, useSession } from '@/lib/session'
import { cn } from '@/lib/utils'
import { useSavedViews } from '@/hooks/use-saved-views'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Input } from '@/components/ui/input'
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover'
import { DataGrid } from '@/components/data-grid'
import { Page } from '@/components/layout/page'
import { StatusBadge } from '@/components/records/status-badge'
import { SavedViewsMenu } from '@/components/saved-views'
import { PARTIES, STATUSES, label, rfiKeys, type Rfi } from './api'
import { Choice } from './choice'
import { useDeepLink } from './deep-link'
import { RfiCreateDialog } from './rfi-create'
import { RfiSheet } from './rfi-sheet'

type Filters = {
  status: string
  ball: string
  overdue: boolean
  discipline: string
  search: string
}

function DueDays({ projectId }: { projectId: number }) {
  const { data } = useQuery({
    queryKey: ['rfis', 'settings', projectId],
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/rfis/settings/{project_id}', {
          params: { path: { project_id: projectId } },
        })
      ),
  })
  const save = useMutation({
    mutationFn: (days: number) =>
      unwrap(
        api.PUT('/api/v1/rfis/settings/{project_id}', {
          params: { path: { project_id: projectId } },
          body: { default_due_days: days },
        })
      ),
    onSuccess: () => toast.success('Saved'),
    onError: handleServerError,
  })
  if (!data) return null
  return (
    <form
      className='grid gap-2'
      onSubmit={(e) => {
        e.preventDefault()
        save.mutate(Number(new FormData(e.currentTarget).get('days')))
      }}
    >
      <label className='text-sm font-medium' htmlFor='rfi-due-days'>
        Days to answer a new RFI
      </label>
      <Input
        id='rfi-due-days'
        name='days'
        type='number'
        min={1}
        max={365}
        defaultValue={data.default_due_days}
      />
      <Button size='sm' type='submit' disabled={save.isPending}>
        Save
      </Button>
    </form>
  )
}

function Register({ projectId }: { projectId: number }) {
  const { t } = useTranslation()
  const session = useSession()
  const linked = useDeepLink()
  const [openId, setOpenId] = useState<number | null>(linked)
  const views = useSavedViews<Rfi>('rfi.register', projectId)
  const [creating, setCreating] = useState(false)
  const [filters, setFilters] = useState<Filters>({
    status: '',
    ball: '',
    overdue: false,
    discipline: '',
    search: '',
  })
  const set = (patch: Partial<Filters>) =>
    setFilters((f) => ({ ...f, ...patch }))
  const query = {
    project_id: projectId,
    status: (filters.status || undefined) as never,
    ball_in_court: filters.ball || undefined,
    overdue: filters.overdue || undefined,
    discipline: filters.discipline || undefined,
    search: filters.search || undefined,
  }
  const { data } = useQuery({
    queryKey: [...rfiKeys.all(projectId), query],
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/rfis/', {
          params: { query: { ...query, items_per_page: 100 } },
        })
      ),
  })
  const rows = useMemo(() => data?.data ?? [], [data])

  const exportUrl = (format: string) => {
    const params = new URLSearchParams({ format })
    for (const [k, v] of Object.entries(query))
      if (v !== undefined) params.set(k, String(v))
    return `/api/v1/rfis/export?${params}`
  }

  const columns = useMemo<ColDef<Rfi>[]>(
    () => [
      { field: 'code', headerName: 'No.', width: 100, sort: 'desc' },
      { field: 'subject', headerName: 'Subject', flex: 2, minWidth: 220 },
      { field: 'discipline', headerName: 'Discipline', width: 130 },
      {
        field: 'status',
        headerName: 'Status',
        width: 120,
        cellRenderer: (p: ICellRendererParams<Rfi>) => (
          <StatusBadge status={p.value} />
        ),
      },
      {
        field: 'ball_in_court',
        headerName: 'Ball in court',
        width: 210,
        valueGetter: (p) =>
          p.data?.ball_in_court
            ? `${label(p.data.ball_in_court)}${
                p.data.bic_user_name || p.data.bic_contact_name
                  ? ` · ${p.data.bic_user_name ?? p.data.bic_contact_name}`
                  : ''
              }`
            : '',
      },
      { field: 'raised_by_name', headerName: 'Raised by', width: 140 },
      { field: 'due_date', headerName: 'Due', width: 110 },
      {
        field: 'days_open',
        headerName: 'Days open',
        width: 120,
        type: 'rightAligned',
        cellRenderer: (p: ICellRendererParams<Rfi>) =>
          p.data ? (
            <span
              className={cn(p.data.overdue && 'font-semibold text-red-600')}
            >
              {p.data.days_open ?? ''}
              {p.data.overdue ? ' · overdue' : ''}
            </span>
          ) : null,
      },
      {
        field: 'priority',
        headerName: 'Priority',
        width: 110,
        cellRenderer: (p: ICellRendererParams<Rfi>) => (
          <StatusBadge status={p.value} />
        ),
      },
      {
        headerName: 'Impact',
        width: 130,
        valueGetter: (p) =>
          p.data
            ? [
                p.data.cost_impact && 'Cost',
                p.data.schedule_impact && 'Schedule',
                p.data.scope_impact && 'Scope',
              ]
                .filter(Boolean)
                .join(', ')
            : '',
      },
      {
        field: 'response_count',
        headerName: 'Replies',
        width: 90,
        type: 'rightAligned',
      },
    ],
    []
  )

  return (
    <>
      <div className='flex flex-wrap items-center gap-2'>
        <SavedViewsMenu views={views} />
        <Choice
          className='h-8 w-36'
          value={filters.status}
          onChange={(status) => set({ status })}
          emptyLabel='All statuses'
          options={STATUSES.map((s) => ({ value: s, label: label(s) }))}
        />
        <Choice
          className='h-8 w-44'
          value={filters.ball}
          onChange={(ball) => set({ ball })}
          emptyLabel='Any ball in court'
          options={[
            { value: 'me', label: 'Waiting on me' },
            ...PARTIES.map((p) => ({ value: p, label: label(p) })),
          ]}
        />
        <Input
          className='h-8 w-36'
          placeholder='Discipline'
          value={filters.discipline}
          onChange={(e) => set({ discipline: e.target.value })}
        />
        <Input
          className='h-8 w-56'
          placeholder='Search'
          value={filters.search}
          onChange={(e) => set({ search: e.target.value })}
        />
        <label className='flex items-center gap-1.5 text-sm'>
          <Checkbox
            checked={filters.overdue}
            onCheckedChange={(c) => set({ overdue: c === true })}
          />
          Overdue only
        </label>
        <div className='ms-auto flex gap-2'>
          {can(session, 'rfi.export') ? (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button size='sm' variant='outline'>
                  <Download /> Export
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align='end'>
                {['xlsx', 'csv', 'pdf'].map((f) => (
                  <DropdownMenuItem key={f} asChild>
                    <a href={exportUrl(f)}>{f.toUpperCase()}</a>
                  </DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>
          ) : null}
          {can(session, 'rfi.update') ? (
            <Popover>
              <PopoverTrigger asChild>
                <Button size='sm' variant='outline' aria-label='RFI settings'>
                  <Settings />
                </Button>
              </PopoverTrigger>
              <PopoverContent align='end' className='w-64'>
                <DueDays projectId={projectId} />
              </PopoverContent>
            </Popover>
          ) : null}
          {can(session, 'rfi.create') ? (
            <Button size='sm' onClick={() => setCreating(true)}>
              <Plus /> Raise RFI
            </Button>
          ) : null}
        </div>
      </div>
      <div className='h-[600px]'>
        <DataGrid<Rfi>
          onGridReady={views.onGridReady}
          rowData={rows}
          columnDefs={columns}
          getRowId={(p) => String(p.data.id)}
          onRowClicked={(e) => e.data && setOpenId(e.data.id)}
          rowClassRules={{ 'cursor-pointer': () => true }}
          overlayNoRowsTemplate={t('rfi.empty')}
        />
      </div>
      <RfiCreateDialog
        projectId={projectId}
        open={creating}
        onClose={() => setCreating(false)}
        onCreated={(rfi) => {
          setCreating(false)
          setOpenId(rfi.id)
        }}
      />
      {openId ? <RfiSheet id={openId} onClose={() => setOpenId(null)} /> : null}
    </>
  )
}

export default function RfiPage() {
  const { t } = useTranslation()
  const project = useCurrentProject()
  return (
    <Page
      title={t('rfi.title')}
      description={t('rfi.description')}
      projectScoped
    >
      {project ? (
        <Register key={project.id} projectId={project.id} />
      ) : (
        <p className='text-sm text-muted-foreground'>{t('rfi.no_project')}</p>
      )}
    </Page>
  )
}
