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
import {
  type ChangeOrder,
  exportUrl,
  REASONS,
  useChangeLog,
  useChangeOrders,
  useCreateChangeOrder,
} from './api'
import { ChangeOrderSheet } from './change-order-sheet'

const FILTERS = [
  'pending',
  'draft',
  'submitted',
  'under_review',
  'approved',
  'rejected',
  'withdrawn',
]

function initialId() {
  const id = Number(new URLSearchParams(window.location.search).get('co'))
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
  const [openId, setOpenId] = useState<number | undefined>(initialId)
  const [draft, setDraft] = useState({ title: '', reason: 'client_request' })
  const { data: orders = [] } = useChangeOrders(projectId, status)
  const { data: log } = useChangeLog(projectId)
  const create = useCreateChangeOrder(projectId)
  const fmt = useMemo(() => money(currency), [currency])
  const format = (v?: string | number | null) => fmt({ value: v })

  const columns = useMemo<ColDef<ChangeOrder>[]>(
    () => [
      {
        field: 'code',
        headerName: t('co.code'),
        width: 90,
        cellClass: 'font-mono',
      },
      {
        field: 'title',
        headerName: t('co.title_field'),
        flex: 1,
        minWidth: 220,
      },
      {
        field: 'reason',
        headerName: t('co.reason'),
        width: 170,
        valueFormatter: (p) => (p.value ? t(`co.why.${p.value}`) : ''),
      },
      {
        field: 'status',
        headerName: t('co.status'),
        width: 130,
        cellRenderer: (p: { value?: string }) => (
          <StatusBadge status={p.value} />
        ),
      },
      { field: 'request_date', headerName: t('co.request_date'), width: 120 },
      {
        field: 'requested_by_name',
        headerName: t('co.requested_by'),
        width: 150,
      },
      {
        field: 'original_total',
        headerName: t('co.original_total'),
        width: 130,
        type: 'rightAligned',
        valueFormatter: fmt,
        cellClass: 'tabular-nums',
      },
      {
        field: 'new_total',
        headerName: t('co.new_total'),
        width: 130,
        type: 'rightAligned',
        valueFormatter: fmt,
        cellClass: 'tabular-nums',
      },
      {
        field: 'total_delta',
        headerName: t('co.delta'),
        width: 130,
        type: 'rightAligned',
        valueFormatter: fmt,
        comparator: (a, b) => Number(a) - Number(b),
        cellClass: (p) =>
          cn(
            'font-medium tabular-nums',
            Number(p.value) < 0 && 'text-red-600',
            Number(p.value) > 0 && 'text-green-600'
          ),
      },
      {
        field: 'time_impact_days',
        headerName: t('co.days'),
        width: 80,
        type: 'rightAligned',
      },
    ],
    [fmt, t]
  )

  return (
    <>
      <div className='grid grid-cols-2 gap-3 lg:grid-cols-4'>
        <Kpi
          label={`${t('co.approved')} (${log?.approved.count ?? 0})`}
          value={format(log?.approved.delta)}
          tone='good'
        />
        <Kpi
          label={`${t('co.pending')} (${log?.pending.count ?? 0})`}
          value={format(log?.pending.delta)}
          tone='warn'
        />
        <Kpi
          label={`${t('co.rejected')} (${log?.rejected.count ?? 0})`}
          value={format(log?.rejected.delta)}
          tone='bad'
        />
        <Kpi
          label={t('co.approved_days')}
          value={`${log?.approved.time_impact_days ?? 0} ${t('co.days')}`}
        />
      </div>

      <div className='flex flex-wrap items-center gap-2'>
        <div className='w-44'>
          <SelectField
            value={status || null}
            onChange={(v) => setStatus(v ?? '')}
            options={FILTERS.map((f) => ({
              value: f,
              label: t(`co.filter.${f}`),
            }))}
            allowNone
            placeholder={t('co.status')}
          />
        </div>
        {can(session, 'change_orders.create') ? (
          <form
            className='flex flex-wrap items-center gap-2'
            onSubmit={(e) => {
              e.preventDefault()
              create.mutate(
                {
                  title: draft.title,
                  reason: draft.reason,
                  time_impact_days: 0,
                  cvr_apply: 'none',
                } as never,
                {
                  onSuccess: (co) => {
                    setDraft({ ...draft, title: '' })
                    setOpenId(co.id)
                  },
                }
              )
            }}
          >
            <Input
              className='h-8 w-64'
              placeholder={t('co.title_field')}
              value={draft.title}
              onChange={(e) => setDraft({ ...draft, title: e.target.value })}
              required
            />
            <div className='w-48'>
              <SelectField
                value={draft.reason}
                onChange={(v) => setDraft({ ...draft, reason: v ?? 'other' })}
                options={REASONS.map((r) => ({
                  value: r,
                  label: t(`co.why.${r}`),
                }))}
              />
            </div>
            <Button size='sm' type='submit' disabled={create.isPending}>
              <Plus /> {t('co.new')}
            </Button>
          </form>
        ) : null}
        {can(session, 'change_orders.export') ? (
          <Button size='sm' variant='outline' className='ms-auto' asChild>
            <a href={exportUrl(projectId)}>
              <Download /> {t('co.export')}
            </a>
          </Button>
        ) : null}
      </div>

      <div className='h-[520px]'>
        <DataGrid<ChangeOrder>
          rowData={orders}
          columnDefs={columns}
          getRowId={(p) => String(p.data.id)}
          onRowClicked={(e) => e.data && setOpenId(e.data.id)}
          rowClass='cursor-pointer'
        />
      </div>

      {openId ? (
        <ChangeOrderSheet
          key={openId}
          projectId={projectId}
          id={openId}
          onClose={() => setOpenId(undefined)}
          format={format}
        />
      ) : null}
    </>
  )
}

export default function ChangeOrdersPage() {
  const { t } = useTranslation()
  const project = useCurrentProject()
  return (
    <Page title={t('co.title')} description={t('co.description')} projectScoped>
      {project ? (
        <Register
          key={project.id}
          projectId={project.id}
          currency={project.currency}
        />
      ) : (
        <p className='text-sm text-muted-foreground'>{t('co.no_project')}</p>
      )}
    </Page>
  )
}
