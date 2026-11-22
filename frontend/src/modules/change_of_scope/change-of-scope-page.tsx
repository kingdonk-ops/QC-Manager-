import { useMemo, useState } from 'react'
import type { ColDef } from 'ag-grid-community'
import { Download, Plus } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useCurrentProject } from '@/stores/use-current-project'
import { money } from '@/lib/format'
import { can, useSession } from '@/lib/session'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { DataGrid } from '@/components/data-grid'
import { Page } from '@/components/layout/page'
import { Kpi, SelectField } from '@/components/records/fields'
import { StatusBadge } from '@/components/records/status-badge'
import { type Card, exportUrl, FILTERS, useCards, useSummary } from './api'
import { CardSheet } from './card-sheet'

function initialId() {
  const id = Number(new URLSearchParams(window.location.search).get('card'))
  return Number.isFinite(id) && id > 0 ? id : undefined
}

function Register({
  projectId,
  currency,
}: {
  projectId: number
  currency: string
}) {
  const { t } = useTranslation()
  const session = useSession()
  const [status, setStatus] = useState('')
  const [search, setSearch] = useState('')
  const [openId, setOpenId] = useState<number | 'new' | undefined>(initialId)
  const { data: cards = [] } = useCards(projectId, status, search)
  const { data: summary } = useSummary(projectId)
  const fmt = useMemo(() => money(currency), [currency])
  const format = (v?: string | number | null) => fmt({ value: v })

  const columns = useMemo<ColDef<Card>[]>(
    () => [
      {
        field: 'code',
        headerName: t('cos.code'),
        width: 100,
        cellClass: 'font-mono',
      },
      {
        field: 'title',
        headerName: t('cos.title_field'),
        flex: 1,
        minWidth: 220,
      },
      {
        field: 'status',
        headerName: t('cos.status'),
        width: 130,
        cellRenderer: (p: { value?: string }) => (
          <StatusBadge status={p.value} />
        ),
      },
      {
        field: 'change_type',
        headerName: t('cos.change_type'),
        width: 150,
        valueFormatter: (p) => (p.value ? t(`cos.type.${p.value}`) : ''),
      },
      { field: 'node_path', headerName: t('cos.location'), width: 200 },
      {
        field: 'client_reference',
        headerName: t('cos.client_reference'),
        width: 130,
      },
      {
        field: 'estimated_amount',
        headerName: t('cos.estimate_total'),
        width: 120,
        type: 'rightAligned',
        valueFormatter: fmt,
        cellClass: 'tabular-nums',
      },
      {
        field: 'expires_in_days',
        headerName: t('cos.expires'),
        width: 100,
        type: 'rightAligned',
        valueFormatter: (p) =>
          p.value === null || p.value === undefined ? '' : `${p.value} d`,
        cellClass: (p) =>
          cn(
            'tabular-nums',
            Number(p.value) <= 3 &&
              p.value !== null &&
              'font-medium text-red-600'
          ),
      },
      {
        field: 'change_order_code',
        headerName: t('cos.change_order'),
        width: 110,
      },
    ],
    [fmt, t]
  )

  return (
    <>
      <div className='grid grid-cols-2 gap-3 lg:grid-cols-4'>
        <Kpi
          label={t('cos.kpi.waiting')}
          value={
            (summary?.by_status.submitted?.count ?? 0) +
            (summary?.by_status.acknowledged?.count ?? 0)
          }
        />
        <Kpi
          label={t('cos.kpi.expiring')}
          value={summary?.expiring_soon ?? 0}
          tone={summary?.expiring_soon ? 'bad' : undefined}
        />
        <Kpi
          label={t('cos.kpi.pending')}
          value={format(summary?.pending_amount)}
          tone='warn'
        />
        <Kpi
          label={t('cos.kpi.approved')}
          value={format(summary?.approved_amount)}
          tone='good'
        />
      </div>
      <div className='flex flex-wrap items-center gap-2'>
        <div className='w-44'>
          <SelectField
            value={status || null}
            onChange={(v) => setStatus(v ?? '')}
            allowNone
            placeholder={t('cos.status')}
            options={FILTERS.map((f) => ({
              value: f,
              label: t(`cos.filter.${f}`),
            }))}
          />
        </div>
        <Input
          className='h-8 w-56'
          placeholder={t('cos.search')}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        {can(session, 'change_of_scope.create') ? (
          <Button size='sm' onClick={() => setOpenId('new')}>
            <Plus /> {t('cos.new')}
          </Button>
        ) : null}
        {can(session, 'change_of_scope.export') ? (
          <Button size='sm' variant='outline' className='ms-auto' asChild>
            <a href={exportUrl(projectId)}>
              <Download /> {t('cos.export')}
            </a>
          </Button>
        ) : null}
      </div>
      <div className='h-[520px]'>
        <DataGrid<Card>
          rowData={cards}
          columnDefs={columns}
          getRowId={(p) => String(p.data.id)}
          onRowClicked={(e) => e.data && setOpenId(e.data.id)}
          rowClass='cursor-pointer'
        />
      </div>
      {openId ? (
        <CardSheet
          key={String(openId)}
          projectId={projectId}
          id={openId}
          onClose={() => setOpenId(undefined)}
          format={(v) => format(v)}
        />
      ) : null}
    </>
  )
}

export default function ChangeOfScopePage() {
  const { t } = useTranslation()
  const project = useCurrentProject()
  return (
    <Page
      title={t('cos.title')}
      description={t('cos.description')}
      projectScoped
    >
      {project ? (
        <Register
          key={project.id}
          projectId={project.id}
          currency={project.currency}
        />
      ) : (
        <p className='text-sm text-muted-foreground'>{t('cos.no_project')}</p>
      )}
    </Page>
  )
}
