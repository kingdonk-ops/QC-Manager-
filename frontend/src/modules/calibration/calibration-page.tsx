import { useMemo, useState } from 'react'
import type { ColDef } from 'ag-grid-community'
import { Download, Plus } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useCurrentProject } from '@/stores/use-current-project'
import { can, useSession } from '@/lib/session'
import { Button } from '@/components/ui/button'
import { DataGrid } from '@/components/data-grid'
import { Page } from '@/components/layout/page'
import { Kpi, SelectField } from '@/components/records/fields'
import { StatusBadge } from '@/components/records/status-badge'
import {
  dueTone,
  type Equipment,
  exportUrl,
  STATUSES,
  useEquipment,
  useSummary,
} from './api'
import { EquipmentSheet } from './equipment-sheet'

function initialId() {
  const id = Number(new URLSearchParams(window.location.search).get('id'))
  return Number.isFinite(id) && id > 0 ? id : undefined
}

function Register({ projectId }: { projectId: number }) {
  const { t } = useTranslation()
  const session = useSession()
  const [status, setStatus] = useState<string | undefined>()
  const [openId, setOpenId] = useState<number | 'new' | undefined>(initialId)
  const { data: rows = [] } = useEquipment(projectId, status)
  const { data: summary } = useSummary(projectId)
  const open = openId === 'new' ? undefined : rows.find((r) => r.id === openId)

  const columns = useMemo<ColDef<Equipment>[]>(
    () => [
      {
        field: 'code',
        headerName: t('calibration.code'),
        width: 100,
        cellClass: 'font-mono',
      },
      {
        field: 'name',
        headerName: t('calibration.name'),
        flex: 1,
        minWidth: 200,
      },
      {
        field: 'equipment_type',
        headerName: t('calibration.type'),
        width: 160,
        valueFormatter: (p) => t(`calibration.type.${p.value}`),
      },
      {
        field: 'serial_number',
        headerName: t('calibration.serial'),
        width: 130,
      },
      {
        field: 'custodian_name',
        headerName: t('calibration.custodian'),
        width: 150,
      },
      {
        field: 'last_calibrated_on',
        headerName: t('calibration.last_calibrated'),
        width: 130,
      },
      {
        field: 'due_on',
        headerName: t('calibration.due'),
        width: 120,
        sort: 'asc',
      },
      {
        field: 'days_to_due',
        headerName: t('calibration.days'),
        width: 90,
        type: 'rightAligned',
      },
      {
        field: 'status',
        headerName: t('calibration.status'),
        width: 160,
        cellRenderer: (p: { value?: string }) => (
          <StatusBadge status={p.value} />
        ),
      },
    ],
    [t]
  )

  return (
    <>
      <div className='grid grid-cols-2 gap-3 lg:grid-cols-5'>
        <Kpi label={t('calibration.total')} value={summary?.total ?? '–'} />
        <Kpi
          label={t('calibration.st.in_service')}
          value={summary?.in_service ?? '–'}
          tone='good'
        />
        <Kpi
          label={t('calibration.st.due')}
          value={summary?.due ?? '–'}
          tone={summary?.due ? 'warn' : undefined}
        />
        <Kpi
          label={t('calibration.st.overdue')}
          value={summary?.overdue ?? '–'}
          tone={summary?.overdue ? 'bad' : undefined}
        />
        <Kpi
          label={t('calibration.st.quarantined')}
          value={summary?.quarantined ?? '–'}
        />
      </div>
      <div className='flex flex-wrap items-center gap-2'>
        <div className='w-48'>
          <SelectField
            value={status}
            onChange={(v) => setStatus(v ?? undefined)}
            options={STATUSES.map((s) => ({
              value: s,
              label: t(`calibration.st.${s}`),
            }))}
            allowNone
            placeholder={t('calibration.status')}
          />
        </div>
        <div className='ms-auto flex gap-2'>
          {can(session, 'calibration.export') ? (
            <Button size='sm' variant='outline' asChild>
              <a href={exportUrl(projectId)}>
                <Download /> {t('calibration.export')}
              </a>
            </Button>
          ) : null}
          {can(session, 'calibration.create') ? (
            <Button size='sm' onClick={() => setOpenId('new')}>
              <Plus /> {t('calibration.new')}
            </Button>
          ) : null}
        </div>
      </div>
      <div className='h-[520px]'>
        <DataGrid<Equipment>
          rowData={rows}
          columnDefs={columns}
          getRowId={(p) => String(p.data.id)}
          getRowClass={(p) => `cursor-pointer ${dueTone(p.data?.status)}`}
          onRowClicked={(e) => e.data && setOpenId(e.data.id)}
        />
      </div>
      {openId !== undefined && (openId === 'new' || open) ? (
        <EquipmentSheet
          key={openId}
          projectId={projectId}
          equipment={open}
          onClose={() => setOpenId(undefined)}
        />
      ) : null}
    </>
  )
}

export default function CalibrationPage() {
  const { t } = useTranslation()
  const project = useCurrentProject()
  return (
    <Page
      title={t('calibration.title')}
      description={t('calibration.description')}
      projectScoped
    >
      {project ? (
        <Register key={project.id} projectId={project.id} />
      ) : (
        <p className='text-sm text-muted-foreground'>
          {t('calibration.no_project')}
        </p>
      )}
    </Page>
  )
}
