import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import type { ColDef, ICellRendererParams } from 'ag-grid-community'
import { FileText, Plus } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { api, unwrap } from '@/api/client'
import { useCurrentProject } from '@/stores/use-current-project'
import { can, useSession } from '@/lib/session'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { DataGrid } from '@/components/data-grid'
import { Page } from '@/components/layout/page'
import { StatusBadge } from '@/components/records/status-badge'
import { coverUrl, label, trKeys, type Transmittal } from './api'
import { BuilderDialog } from './builder-dialog'
import { Choice } from './choice'
import { useDeepLink } from './deep-link'
import { TransmittalSheet } from './transmittal-sheet'

const STATUSES = ['draft', 'sent', 'partially_acknowledged', 'acknowledged']

const DOT: Record<string, string> = {
  pending: 'bg-muted-foreground/40',
  no_email: 'bg-amber-500',
  sent: 'bg-blue-500',
  received: 'bg-sky-400',
  acknowledged: 'bg-green-500',
}

function Delivery({ t }: { t: Transmittal }) {
  return (
    <span className='flex h-full items-center gap-1'>
      {(t.recipients ?? []).map((r) => (
        <Tooltip key={r.id}>
          <TooltipTrigger asChild>
            <span
              className={cn('size-2.5 rounded-full', DOT[r.delivery ?? ''])}
              aria-label={`${r.name}: ${label(r.delivery ?? 'pending')}`}
            />
          </TooltipTrigger>
          <TooltipContent>
            {r.name}: {label(r.delivery ?? 'pending')}
          </TooltipContent>
        </Tooltip>
      ))}
      <span className='ms-1 text-xs text-muted-foreground'>
        {t.acknowledged_count}/{t.recipient_count} acknowledged
      </span>
    </span>
  )
}

function Register({ projectId }: { projectId: number }) {
  const { t } = useTranslation()
  const session = useSession()
  const linked = useDeepLink()
  const [openId, setOpenId] = useState<number | null>(linked)
  const [building, setBuilding] = useState(false)
  const [status, setStatus] = useState('')
  const [search, setSearch] = useState('')
  const { data } = useQuery({
    queryKey: [...trKeys.all(projectId), status, search],
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/transmittals/', {
          params: {
            query: {
              project_id: projectId,
              status: (status || undefined) as never,
              search: search || undefined,
              items_per_page: 100,
            },
          },
        })
      ),
  })
  const rows = useMemo(() => data?.data ?? [], [data])

  const columns = useMemo<ColDef<Transmittal>[]>(
    () => [
      { field: 'code', headerName: 'No.', width: 100, sort: 'desc' },
      { field: 'subject', headerName: 'Subject', flex: 2, minWidth: 220 },
      {
        field: 'purpose',
        headerName: 'Purpose',
        width: 150,
        valueFormatter: (p) => (p.value ? label(p.value) : ''),
      },
      {
        field: 'status',
        headerName: 'Status',
        width: 190,
        cellRenderer: (p: ICellRendererParams<Transmittal>) => (
          <StatusBadge status={p.value} />
        ),
      },
      {
        field: 'document_count',
        headerName: 'Docs',
        width: 80,
        type: 'rightAligned',
      },
      {
        headerName: 'Delivery',
        width: 240,
        sortable: false,
        filter: false,
        cellRenderer: (p: ICellRendererParams<Transmittal>) =>
          p.data ? <Delivery t={p.data} /> : null,
      },
      {
        field: 'sent_at',
        headerName: 'Sent',
        width: 120,
        valueFormatter: (p) =>
          p.value ? new Date(p.value).toLocaleDateString() : '',
      },
      { field: 'response_due', headerName: 'Response due', width: 130 },
      {
        headerName: '',
        width: 60,
        sortable: false,
        filter: false,
        cellRenderer: (p: ICellRendererParams<Transmittal>) =>
          p.data ? (
            <a
              className='flex h-full items-center'
              href={coverUrl(p.data.id)}
              target='_blank'
              rel='noreferrer'
              aria-label='Cover sheet'
              onClick={(e) => e.stopPropagation()}
            >
              <FileText className='size-4' />
            </a>
          ) : null,
      },
    ],
    []
  )

  return (
    <>
      <div className='flex flex-wrap items-center gap-2'>
        <Choice
          className='h-8 w-52'
          value={status}
          onChange={setStatus}
          emptyLabel='All statuses'
          options={STATUSES.map((s) => ({ value: s, label: label(s) }))}
        />
        <Input
          className='h-8 w-56'
          placeholder='Search number or subject'
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        {can(session, 'transmittals.create') ? (
          <Button
            size='sm'
            className='ms-auto'
            onClick={() => setBuilding(true)}
          >
            <Plus /> New transmittal
          </Button>
        ) : null}
      </div>
      <div className='h-[600px]'>
        <DataGrid
          rowData={rows}
          columnDefs={columns}
          getRowId={(p) => String(p.data.id)}
          onRowClicked={(e) => e.data && setOpenId(e.data.id)}
          rowClassRules={{ 'cursor-pointer': () => true }}
          overlayNoRowsTemplate={t('transmittals.empty')}
        />
      </div>
      {building ? (
        <BuilderDialog
          projectId={projectId}
          onClose={() => setBuilding(false)}
          onCreated={(created) => {
            setBuilding(false)
            setOpenId(created.id)
          }}
        />
      ) : null}
      {openId ? (
        <TransmittalSheet id={openId} onClose={() => setOpenId(null)} />
      ) : null}
    </>
  )
}

export default function TransmittalsPage() {
  const { t } = useTranslation()
  const project = useCurrentProject()
  return (
    <Page
      title={t('transmittals.title')}
      description={t('transmittals.description')}
      projectScoped
    >
      {project ? (
        <Register key={project.id} projectId={project.id} />
      ) : (
        <p className='text-sm text-muted-foreground'>
          {t('transmittals.no_project')}
        </p>
      )}
    </Page>
  )
}
