import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import type { ColDef, ICellRendererParams } from 'ag-grid-community'
import { Download, Plus } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { api, unwrap } from '@/api/client'
import { useCurrentProject } from '@/stores/use-current-project'
import { can, useSession } from '@/lib/session'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Input } from '@/components/ui/input'
import { DataGrid } from '@/components/data-grid'
import { Page } from '@/components/layout/page'
import { StatusBadge } from '@/components/records/status-badge'
import {
  STATUSES,
  TYPES,
  corKeys,
  label,
  typeName,
  useContactOptions,
  type Item,
} from './api'
import { Choice } from './choice'
import { useDeepLink } from './deep-link'
import { ItemDialog } from './item-form'
import { DirectionIcon, ItemSheet } from './item-sheet'

type Filters = {
  type: string
  direction: string
  status: string
  contact: string
  overdue: boolean
  search: string
}

function Register({ projectId }: { projectId: number }) {
  const { t } = useTranslation()
  const session = useSession()
  const linked = useDeepLink()
  const { data: contacts = [] } = useContactOptions()
  const [openId, setOpenId] = useState<number | null>(linked)
  const [dialog, setDialog] = useState<{ replyTo: Item | null } | null>(null)
  const [filters, setFilters] = useState<Filters>({
    type: '',
    direction: '',
    status: '',
    contact: '',
    overdue: false,
    search: '',
  })
  const set = (patch: Partial<Filters>) =>
    setFilters((f) => ({ ...f, ...patch }))
  const query = {
    project_id: projectId,
    type: (filters.type || undefined) as never,
    direction: (filters.direction || undefined) as never,
    status: (filters.status || undefined) as never,
    contact_id: filters.contact ? Number(filters.contact) : undefined,
    overdue: filters.overdue || undefined,
    search: filters.search || undefined,
  }
  const { data } = useQuery({
    queryKey: [...corKeys.all(projectId), query],
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/correspondence/', {
          params: { query: { ...query, items_per_page: 100 } },
        })
      ),
  })
  const rows = useMemo(() => data?.data ?? [], [data])

  const exportUrl = (format: string) => {
    const params = new URLSearchParams({ format })
    for (const [k, v] of Object.entries(query))
      if (v !== undefined) params.set(k, String(v))
    return `/api/v1/correspondence/export?${params}`
  }

  const columns = useMemo<ColDef<Item>[]>(
    () => [
      {
        field: 'direction',
        headerName: '',
        width: 50,
        cellRenderer: (p: ICellRendererParams<Item>) => (
          <span className='flex h-full items-center'>
            <DirectionIcon direction={p.value} />
          </span>
        ),
      },
      { field: 'reference', headerName: 'Reference', width: 140, sort: 'desc' },
      {
        headerName: 'Type',
        width: 140,
        valueGetter: (p) => (p.data ? typeName(p.data) : ''),
      },
      { field: 'subject', headerName: 'Subject', flex: 2, minWidth: 240 },
      { field: 'sender_name', headerName: 'From', width: 170 },
      {
        headerName: 'To',
        width: 190,
        valueGetter: (p) =>
          (p.data?.recipients ?? []).map((r) => r.name).join(', '),
      },
      {
        headerName: 'Date',
        width: 110,
        valueGetter: (p) => p.data?.date_sent ?? p.data?.date_received ?? '',
      },
      {
        field: 'response_required_by',
        headerName: 'Response by',
        width: 140,
        cellRenderer: (p: ICellRendererParams<Item>) =>
          p.data?.response_required_by ? (
            <span
              className={cn(p.data.overdue && 'font-semibold text-red-600')}
            >
              {p.data.response_required_by}
              {p.data.overdue ? ' · overdue' : ''}
            </span>
          ) : null,
      },
      {
        field: 'status',
        headerName: 'Status',
        width: 160,
        cellRenderer: (p: ICellRendererParams<Item>) => (
          <StatusBadge status={p.value} />
        ),
      },
      {
        field: 'reply_count',
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
        <Choice
          className='h-8 w-40'
          value={filters.type}
          onChange={(type) => set({ type })}
          emptyLabel='All types'
          options={TYPES.map((v) => ({ value: v, label: label(v) }))}
        />
        <Choice
          className='h-8 w-36'
          value={filters.direction}
          onChange={(direction) => set({ direction })}
          emptyLabel='In and out'
          options={[
            { value: 'incoming', label: 'Incoming' },
            { value: 'outgoing', label: 'Outgoing' },
          ]}
        />
        <Choice
          className='h-8 w-44'
          value={filters.status}
          onChange={(status) => set({ status })}
          emptyLabel='All statuses'
          options={STATUSES.map((v) => ({ value: v, label: label(v) }))}
        />
        <Choice
          className='h-8 w-48'
          value={filters.contact}
          onChange={(contact) => set({ contact })}
          emptyLabel='Any contact'
          options={contacts.map((c) => ({
            value: String(c.id),
            label: c.name,
          }))}
        />
        <Input
          className='h-8 w-56'
          placeholder='Search subject and body'
          value={filters.search}
          onChange={(e) => set({ search: e.target.value })}
        />
        <label className='flex items-center gap-1.5 text-sm'>
          <Checkbox
            checked={filters.overdue}
            onCheckedChange={(c) => set({ overdue: c === true })}
          />
          Response overdue
        </label>
        <div className='ms-auto flex gap-2'>
          {can(session, 'correspondence.export') ? (
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
          {can(session, 'correspondence.create') ? (
            <Button size='sm' onClick={() => setDialog({ replyTo: null })}>
              <Plus /> Register
            </Button>
          ) : null}
        </div>
      </div>
      <div className='h-[600px]'>
        <DataGrid
          rowData={rows}
          columnDefs={columns}
          getRowId={(p) => String(p.data.id)}
          onRowClicked={(e) => e.data && setOpenId(e.data.id)}
          rowClassRules={{ 'cursor-pointer': () => true }}
          overlayNoRowsTemplate={t('correspondence.empty')}
        />
      </div>
      {dialog ? (
        <ItemDialog
          key={dialog.replyTo?.id ?? 'new'}
          projectId={projectId}
          replyTo={dialog.replyTo}
          open
          onClose={() => setDialog(null)}
          onCreated={(item) => {
            setDialog(null)
            setOpenId(item.id)
          }}
        />
      ) : null}
      {openId ? (
        <ItemSheet
          id={openId}
          onClose={() => setOpenId(null)}
          onOpen={setOpenId}
          onReply={(item) => setDialog({ replyTo: item })}
        />
      ) : null}
    </>
  )
}

export default function CorrespondencePage() {
  const { t } = useTranslation()
  const project = useCurrentProject()
  return (
    <Page
      title={t('correspondence.title')}
      description={t('correspondence.description')}
      projectScoped
    >
      {project ? (
        <Register key={project.id} projectId={project.id} />
      ) : (
        <p className='text-sm text-muted-foreground'>
          {t('correspondence.no_project')}
        </p>
      )}
    </Page>
  )
}
