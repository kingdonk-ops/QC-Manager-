import { useMemo, useState } from 'react'
import type { ColDef } from 'ag-grid-community'
import { Download, Plus } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useCurrentProject } from '@/stores/use-current-project'
import { money } from '@/lib/format'
import { can, useSession } from '@/lib/session'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { DataGrid } from '@/components/data-grid'
import { Page } from '@/components/layout/page'
import { Kpi, SelectField } from '@/components/records/fields'
import { StatusBadge } from '@/components/records/status-badge'
import {
  exportUrl,
  type PurchaseOrder,
  STATUSES,
  type Summary,
  useCompanies,
  useCreatePurchaseOrder,
  usePurchaseOrders,
  useSummary,
} from './api'
import { PoSheet } from './po-sheet'

function initialId() {
  const id = Number(new URLSearchParams(window.location.search).get('po'))
  return Number.isFinite(id) && id > 0 ? id : undefined
}

function Deliveries({
  summary,
  format,
  onOpen,
}: {
  summary?: Summary
  format: (v?: string | number | null) => string
  onOpen: (id: number) => void
}) {
  const { t } = useTranslation()
  const rows = summary?.outstanding ?? []
  return (
    <Card>
      <CardHeader>
        <CardTitle className='text-base'>{t('po.deliveries')}</CardTitle>
      </CardHeader>
      <CardContent>
        {rows.length ? (
          <ul className='divide-y text-sm'>
            {rows.map((d) => (
              <li key={d.purchase_order_id}>
                <button
                  type='button'
                  className={cn(
                    'flex w-full flex-wrap items-center gap-2 py-1.5 text-left hover:bg-muted/50',
                    d.overdue && 'text-red-600'
                  )}
                  onClick={() => onOpen(d.purchase_order_id)}
                >
                  <span className='w-20 font-mono'>{d.code}</span>
                  <span className='min-w-0 flex-1 truncate'>
                    {d.supplier_name ?? '—'}
                    {d.title ? ` · ${d.title}` : ''}
                  </span>
                  <StatusBadge status={d.status} />
                  <span className='w-28 text-right'>
                    {d.required_by ?? '—'}
                    {d.overdue ? ` (+${d.days_overdue}d)` : ''}
                  </span>
                  <span className='w-28 text-right tabular-nums'>
                    {format(d.outstanding_net)}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <p className='text-sm text-muted-foreground'>
            {t('po.no_deliveries')}
          </p>
        )}
      </CardContent>
    </Card>
  )
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
  const [overdue, setOverdue] = useState(false)
  const [openId, setOpenId] = useState<number | undefined>(initialId)
  const [supplier, setSupplier] = useState<string | null>(null)
  const { data: orders = [] } = usePurchaseOrders(projectId, status, overdue)
  const { data: summary } = useSummary(projectId)
  const { data: companies = [] } = useCompanies('')
  const create = useCreatePurchaseOrder(projectId)
  const fmt = useMemo(() => money(currency), [currency])
  const format = (v?: string | number | null) => fmt({ value: v })

  const columns = useMemo<ColDef<PurchaseOrder>[]>(
    () => [
      {
        field: 'code',
        headerName: t('po.code'),
        width: 90,
        cellClass: 'font-mono',
      },
      { field: 'supplier_name', headerName: t('po.supplier'), width: 180 },
      { field: 'title', headerName: t('po.reference'), flex: 1, minWidth: 160 },
      {
        field: 'status',
        headerName: t('po.status'),
        width: 150,
        cellRenderer: (p: { value?: string }) => (
          <StatusBadge status={p.value} />
        ),
      },
      { field: 'order_date', headerName: t('po.order_date'), width: 115 },
      {
        field: 'required_by',
        headerName: t('po.required_by'),
        width: 115,
        cellClass: (p) => (p.data?.overdue ? 'text-red-600 font-medium' : ''),
      },
      {
        field: 'gross_total',
        headerName: t('po.gross'),
        width: 130,
        type: 'rightAligned',
        valueFormatter: fmt,
        cellClass: 'tabular-nums',
        comparator: (a, b) => Number(a) - Number(b),
      },
      {
        field: 'received_net',
        headerName: t('po.received_value'),
        width: 130,
        type: 'rightAligned',
        valueFormatter: fmt,
        cellClass: 'tabular-nums',
      },
      {
        field: 'received_pct',
        headerName: '%',
        width: 70,
        type: 'rightAligned',
      },
    ],
    [fmt, t]
  )

  return (
    <>
      <div className='grid grid-cols-2 gap-3 lg:grid-cols-4'>
        <Kpi label={t('po.committed')} value={format(summary?.committed_net)} />
        <Kpi
          label={t('po.received_value')}
          value={format(summary?.received_net)}
          tone='good'
        />
        <Kpi
          label={t('po.outstanding')}
          value={format(summary?.outstanding_net)}
          tone='warn'
        />
        <Kpi
          label={t('po.overdue_deliveries')}
          value={summary?.overdue_count ?? '–'}
          tone={summary?.overdue_count ? 'bad' : undefined}
        />
      </div>

      <Deliveries summary={summary} format={format} onOpen={setOpenId} />

      <div className='flex flex-wrap items-center gap-2'>
        <div className='w-48'>
          <SelectField
            value={status || null}
            onChange={(v) => setStatus(v ?? '')}
            options={STATUSES.map((s) => ({
              value: s,
              label: t(`po.st.${s}`),
            }))}
            allowNone
            placeholder={t('po.status')}
          />
        </div>
        <label className='flex items-center gap-1.5 text-sm'>
          <input
            type='checkbox'
            checked={overdue}
            onChange={(e) => setOverdue(e.target.checked)}
          />
          {t('po.overdue_only')}
        </label>
        {can(session, 'procurement.create') ? (
          <form
            className='flex flex-wrap items-center gap-2'
            onSubmit={(e) => {
              e.preventDefault()
              create.mutate(
                {
                  supplier_company_id: supplier ? Number(supplier) : undefined,
                },
                { onSuccess: (po) => setOpenId(po.id) }
              )
            }}
          >
            <div className='w-56'>
              <SelectField
                value={supplier}
                onChange={setSupplier}
                options={companies.map((c) => ({
                  value: String(c.id),
                  label: c.name,
                }))}
                allowNone
                placeholder={t('po.supplier')}
              />
            </div>
            <Button size='sm' type='submit' disabled={create.isPending}>
              <Plus /> {t('po.new')}
            </Button>
          </form>
        ) : null}
        {can(session, 'procurement.export') ? (
          <Button size='sm' variant='outline' className='ms-auto' asChild>
            <a href={exportUrl(projectId)}>
              <Download /> {t('po.export')}
            </a>
          </Button>
        ) : null}
      </div>

      <div className='h-[480px]'>
        <DataGrid<PurchaseOrder>
          rowData={orders}
          columnDefs={columns}
          getRowId={(p) => String(p.data.id)}
          onRowClicked={(e) => e.data && setOpenId(e.data.id)}
          rowClass='cursor-pointer'
        />
      </div>

      {openId ? (
        <PoSheet
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

export default function ProcurementPage() {
  const { t } = useTranslation()
  const project = useCurrentProject()
  return (
    <Page title={t('po.title')} description={t('po.description')} projectScoped>
      {project ? (
        <Register
          key={project.id}
          projectId={project.id}
          currency={project.currency}
        />
      ) : (
        <p className='text-sm text-muted-foreground'>{t('po.no_project')}</p>
      )}
    </Page>
  )
}
