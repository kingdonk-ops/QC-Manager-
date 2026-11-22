import { useMemo, useState } from 'react'
import type { ColDef, ICellRendererParams } from 'ag-grid-community'
import { Settings2, Upload } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useCurrentProject } from '@/stores/use-current-project'
import { can, useSession } from '@/lib/session'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { DataGrid } from '@/components/data-grid'
import { Page } from '@/components/layout/page'
import { StatusBadge } from '@/components/records/status-badge'
import {
  STATES,
  useConvention,
  useCounts,
  useDocuments,
  type CdeDocument,
  type CdeState,
} from './api'
import { DocumentSheet } from './document-sheet'
import { NamingDialog } from './naming-dialog'
import { UploadDialog } from './upload-dialog'

type View = CdeState | 'awaiting'

function Cde({ projectId }: { projectId: number }) {
  const { t } = useTranslation()
  const session = useSession()
  const [view, setView] = useState<View>('wip')
  const [search, setSearch] = useState('')
  const [dialog, setDialog] = useState<'upload' | 'naming' | null>(null)
  const [open, setOpen] = useState<number | null>(() => {
    const id = Number(new URLSearchParams(window.location.search).get('id'))
    return id > 0 ? id : null
  })
  const { data: counts } = useCounts(projectId)
  const { data: convention } = useConvention(projectId)
  const { data } = useDocuments(projectId, {
    state: view === 'awaiting' ? undefined : view,
    awaiting_me: view === 'awaiting',
    search,
  })
  const rows = useMemo(() => data?.data ?? [], [data])

  const columns = useMemo<ColDef<CdeDocument>[]>(
    () => [
      {
        field: 'name',
        headerName: 'Container',
        width: 260,
        cellClass: 'font-mono',
      },
      { field: 'title', headerName: 'Title', flex: 2, minWidth: 200 },
      { field: 'revision', headerName: 'Rev', width: 80 },
      {
        field: 'suitability',
        headerName: 'Suitability',
        width: 110,
      },
      {
        field: 'state',
        headerName: 'State',
        width: 130,
        cellRenderer: (p: ICellRendererParams<CdeDocument>) => (
          <span className='flex h-full items-center gap-1'>
            <StatusBadge status={p.value} />
            {p.data?.pending_state ? (
              <StatusBadge status={`pending ${p.data.pending_state}`} />
            ) : null}
          </span>
        ),
      },
      { field: 'file_name', headerName: 'File', flex: 1, minWidth: 160 },
      { field: 'created_by_name', headerName: 'Author', width: 150 },
      {
        field: 'updated_at',
        headerName: 'Updated',
        width: 160,
        valueFormatter: (p) =>
          p.value ? new Date(p.value).toLocaleString() : '',
      },
    ],
    []
  )

  const count = (v: View) =>
    v === 'awaiting' ? (counts?.awaiting_me ?? 0) : (counts?.[v] ?? 0)

  return (
    <>
      <div className='flex flex-wrap items-center gap-2'>
        <Tabs value={view} onValueChange={(v) => setView(v as View)}>
          <TabsList>
            {STATES.map((s) => (
              <TabsTrigger key={s.id} value={s.id} className='gap-1.5'>
                {s.label}
                <Badge variant='secondary' className='h-5 px-1.5 text-[11px]'>
                  {count(s.id)}
                </Badge>
              </TabsTrigger>
            ))}
            {can(session, 'cde.review') || can(session, 'cde.approve') ? (
              <TabsTrigger value='awaiting' className='gap-1.5'>
                Waiting for my approval
                <Badge
                  variant={count('awaiting') ? 'default' : 'secondary'}
                  className='h-5 px-1.5 text-[11px]'
                >
                  {count('awaiting')}
                </Badge>
              </TabsTrigger>
            ) : null}
          </TabsList>
        </Tabs>
        <Input
          className='h-8 w-60'
          placeholder='Search name or title'
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <div className='ms-auto flex gap-2'>
          {can(session, 'cde.manage') && convention ? (
            <Button
              size='sm'
              variant='outline'
              onClick={() => setDialog('naming')}
            >
              <Settings2 /> Naming convention
            </Button>
          ) : null}
          {can(session, 'cde.upload') ? (
            <Button size='sm' onClick={() => setDialog('upload')}>
              <Upload /> Upload
            </Button>
          ) : null}
        </div>
      </div>
      <div className='h-[560px]'>
        <DataGrid
          rowData={rows}
          columnDefs={columns}
          getRowId={(p) => String(p.data.id)}
          onRowClicked={(e) => e.data && setOpen(e.data.id)}
          rowClass='cursor-pointer'
          overlayNoRowsTemplate={t('cde.empty')}
        />
      </div>
      {dialog === 'upload' ? (
        <UploadDialog
          projectId={projectId}
          onClose={() => setDialog(null)}
          onDone={(id) => {
            setDialog(null)
            setView('wip')
            setOpen(id)
          }}
        />
      ) : null}
      {dialog === 'naming' && convention ? (
        <NamingDialog
          projectId={projectId}
          convention={convention}
          onClose={() => setDialog(null)}
        />
      ) : null}
      <DocumentSheet
        id={open}
        requireShareApproval={convention?.require_share_approval ?? true}
        onClose={() => setOpen(null)}
      />
    </>
  )
}

export default function CdePage() {
  const { t } = useTranslation()
  const project = useCurrentProject()
  return (
    <Page
      title={t('cde.title')}
      description={t('cde.description')}
      projectScoped
    >
      {project ? (
        <Cde key={project.id} projectId={project.id} />
      ) : (
        <p className='text-sm text-muted-foreground'>Choose a project.</p>
      )}
    </Page>
  )
}
