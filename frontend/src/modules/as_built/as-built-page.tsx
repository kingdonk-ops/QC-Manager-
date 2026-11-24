import { useMemo, useState } from 'react'
import type { ColDef } from 'ag-grid-community'
import { Plus } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useCurrentProject } from '@/stores/use-current-project'
import { can, useSession } from '@/lib/session'
import { Button } from '@/components/ui/button'
import { DataGrid } from '@/components/data-grid'
import { Page } from '@/components/layout/page'
import { NativeSelect } from '@/components/native-select'
import { StatusBadge } from '@/components/records/status-badge'
import { type AsBuilt, useRecords } from './api'
import { STATUSES, TOLERANCE_RESULTS, toleranceTone } from './as-built'
import { CreateRecordDialog } from './as-built-dialogs'
import { AsBuiltSheet } from './as-built-sheet'

function initialId() {
  const id = Number(new URLSearchParams(window.location.search).get('id'))
  return Number.isFinite(id) && id > 0 ? id : null
}

function Register({ projectId }: { projectId: number }) {
  const { t } = useTranslation()
  const session = useSession()
  const [status, setStatus] = useState('')
  const [tolerance, setTolerance] = useState('')
  const [openId, setOpenId] = useState<number | null>(initialId)
  const [creating, setCreating] = useState(false)
  const { data: rows = [] } = useRecords(projectId, status, tolerance)
  const open = rows.find((r) => r.id === openId)

  const columns = useMemo<ColDef<AsBuilt>[]>(
    () => [
      {
        field: 'number',
        headerName: t('as_built.number'),
        width: 120,
        cellClass: 'font-mono',
      },
      {
        field: 'title',
        headerName: t('as_built.title'),
        flex: 1,
        minWidth: 220,
      },
      {
        field: 'discipline',
        headerName: t('as_built.discipline'),
        width: 140,
      },
      {
        field: 'location',
        headerName: t('as_built.location'),
        width: 160,
      },
      {
        field: 'capture_method',
        headerName: t('as_built.capture_method'),
        width: 170,
        valueFormatter: (p) => t(`as_built.capture.${p.value}`),
      },
      {
        field: 'measured_value',
        headerName: t('as_built.measured_value'),
        width: 130,
        type: 'rightAligned',
      },
      {
        field: 'tolerance_result',
        headerName: t('as_built.tolerance_result'),
        width: 170,
        cellRenderer: (p: { value?: string }) =>
          p.value ? (
            <span
              className={`rounded px-1.5 py-0.5 text-xs ${toleranceTone(p.value)}`}
            >
              {t(`as_built.tolerance.${p.value}`)}
            </span>
          ) : null,
      },
      {
        field: 'status',
        headerName: t('as_built.status'),
        width: 130,
        cellRenderer: (p: { value?: string }) => (
          <StatusBadge status={p.value} />
        ),
      },
    ],
    [t]
  )

  return (
    <>
      <div className='flex flex-wrap items-center gap-2'>
        <NativeSelect
          className='h-8 w-44'
          aria-label={t('as_built.status')}
          placeholder={t('as_built.all_statuses')}
          options={STATUSES.map((s) => ({
            value: s,
            label: t(`as_built.status.${s}`),
          }))}
          value={status}
          onChange={(e) => setStatus(e.target.value)}
        />
        <NativeSelect
          className='h-8 w-52'
          aria-label={t('as_built.tolerance_result')}
          placeholder={t('as_built.all_results')}
          options={TOLERANCE_RESULTS.map((r) => ({
            value: r,
            label: t(`as_built.tolerance.${r}`),
          }))}
          value={tolerance}
          onChange={(e) => setTolerance(e.target.value)}
        />
        {can(session, 'as_built.create') ? (
          <Button
            size='sm'
            className='ms-auto'
            onClick={() => setCreating(true)}
          >
            <Plus /> {t('as_built.new')}
          </Button>
        ) : null}
      </div>
      <div className='h-[520px]'>
        <DataGrid<AsBuilt>
          rowData={rows}
          columnDefs={columns}
          getRowId={(p) => String(p.data.id)}
          rowClass='cursor-pointer'
          onRowClicked={(e) => e.data && setOpenId(e.data.id)}
        />
      </div>
      {open ? (
        <AsBuiltSheet
          key={open.id}
          record={open}
          onClose={() => setOpenId(null)}
        />
      ) : null}
      {creating ? (
        <CreateRecordDialog
          projectId={projectId}
          onClose={() => setCreating(false)}
        />
      ) : null}
    </>
  )
}

export default function AsBuiltPage() {
  const { t } = useTranslation()
  const project = useCurrentProject()
  return (
    <Page
      title={t('as_built.page_title')}
      description={t('as_built.description')}
      projectScoped
    >
      {project ? (
        <Register key={project.id} projectId={project.id} />
      ) : (
        <p className='text-sm text-muted-foreground'>
          {t('as_built.no_project')}
        </p>
      )}
    </Page>
  )
}
