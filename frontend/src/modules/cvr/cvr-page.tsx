import { useMemo, useRef, useState } from 'react'
import type {
  CellClassParams,
  ColDef,
  ValueGetterParams,
} from 'ag-grid-community'
import type { AgGridReact } from 'ag-grid-react'
import { Download, Plus, Trash2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useCurrentProject } from '@/stores/use-current-project'
import { money } from '@/lib/format'
import { can, useSession } from '@/lib/session'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { DataGrid } from '@/components/data-grid'
import { Page } from '@/components/layout/page'
import {
  type CostHead,
  useAddCostHead,
  useCashflow,
  useCostHeads,
  useDeleteCostHead,
  useSummary,
  useUpdateCostHead,
} from './api'
import { CashflowChart } from './cashflow-chart'

type MoneyField =
  | 'budget'
  | 'cost_to_date'
  | 'value_to_date'
  | 'forecast_cost'
  | 'forecast_value'

const marginClass = (params: CellClassParams) =>
  cn(
    'font-medium',
    Number(params.value) < 0
      ? 'text-red-600'
      : Number(params.value) > 0 && 'text-green-600'
  )

function Kpi({
  label,
  value,
  tone,
}: {
  label: string
  value: string
  tone?: 'good' | 'bad'
}) {
  return (
    <Card className='gap-1 py-3'>
      <CardHeader className='px-4'>
        <CardTitle className='text-xs font-medium text-muted-foreground'>
          {label}
        </CardTitle>
      </CardHeader>
      <CardContent className='px-4'>
        <p
          className={cn(
            'text-lg font-semibold tabular-nums',
            tone === 'good' && 'text-green-600',
            tone === 'bad' && 'text-red-600'
          )}
        >
          {value}
        </p>
      </CardContent>
    </Card>
  )
}

function Reconciliation({
  projectId,
  currency,
}: {
  projectId: number
  currency: string
}) {
  const { t } = useTranslation()
  const session = useSession()
  const editable = can(session, 'cvr.edit')
  const grid = useRef<AgGridReact<CostHead>>(null)
  const { data: heads = [] } = useCostHeads(projectId)
  const { data: summary } = useSummary(projectId)
  const { data: cashflow = [] } = useCashflow(projectId)
  const update = useUpdateCostHead(projectId)
  const add = useAddCostHead(projectId)
  const { mutate: removeHead } = useDeleteCostHead(projectId)
  const [draft, setDraft] = useState({ code: '', description: '' })
  const fmt = useMemo(() => money(currency), [currency])
  const format = (v?: string | number | null) => fmt({ value: v })

  const columns = useMemo<ColDef<CostHead>[]>(() => {
    const moneyCol = (
      field: MoneyField,
      headerName: string
    ): ColDef<CostHead> => ({
      field,
      headerName,
      type: 'rightAligned',
      editable: (p) => editable && !p.node.rowPinned,
      valueFormatter: fmt,
      valueParser: (p) => {
        const n = Number(String(p.newValue).replace(/[^0-9.-]/g, ''))
        return Number.isFinite(n) ? n.toFixed(2) : p.oldValue
      },
      cellClass: 'tabular-nums',
      width: 140,
    })
    const margin = (
      headerName: string,
      value: string,
      cost: string
    ): ColDef<CostHead> => ({
      headerName,
      type: 'rightAligned',
      valueGetter: (p: ValueGetterParams<CostHead>) =>
        p.data
          ? Number(p.data[value as keyof CostHead]) -
            Number(p.data[cost as keyof CostHead])
          : null,
      valueFormatter: fmt,
      cellClass: marginClass,
      width: 140,
    })
    return [
      {
        field: 'code',
        headerName: t('cvr.code'),
        width: 90,
        pinned: 'left',
        cellClass: 'font-mono',
        editable: (p) => editable && !p.node.rowPinned,
      },
      {
        field: 'description',
        headerName: t('cvr.head'),
        flex: 1,
        minWidth: 220,
        pinned: 'left',
        editable: (p) => editable && !p.node.rowPinned,
      },
      moneyCol('budget', t('cvr.budget')),
      moneyCol('cost_to_date', t('cvr.cost')),
      moneyCol('value_to_date', t('cvr.value')),
      margin(t('cvr.margin'), 'value_to_date', 'cost_to_date'),
      moneyCol('forecast_cost', t('cvr.forecast_cost')),
      moneyCol('forecast_value', t('cvr.forecast_value')),
      margin(t('cvr.forecast_margin'), 'forecast_value', 'forecast_cost'),
      ...(editable
        ? [
            {
              headerName: '',
              width: 48,
              sortable: false,
              filter: false,
              cellRenderer: (p: {
                data?: CostHead
                node: { rowPinned?: string | null }
              }) =>
                p.data && !p.node.rowPinned ? (
                  <button
                    className='text-muted-foreground hover:text-red-600'
                    aria-label='Delete'
                    onClick={() => removeHead(p.data!.id)}
                  >
                    <Trash2 className='size-4' />
                  </button>
                ) : null,
            } satisfies ColDef<CostHead>,
          ]
        : []),
    ]
  }, [editable, fmt, removeHead, t])

  const totals = useMemo(() => {
    if (!summary) return []
    return [
      {
        id: -1,
        project_id: projectId,
        code: '',
        description: t('common.total'),
        sort_order: 0,
        budget: summary.budget,
        cost_to_date: summary.cost_to_date,
        value_to_date: summary.value_to_date,
        forecast_cost: summary.forecast_cost,
        forecast_value: summary.forecast_value,
        margin_to_date: summary.margin_to_date,
        forecast_margin: summary.forecast_margin,
      } as CostHead,
    ]
  }, [summary, projectId, t])

  const tone = (v?: string) =>
    Number(v) < 0 ? 'bad' : Number(v) > 0 ? 'good' : undefined

  return (
    <>
      <div className='grid grid-cols-2 gap-3 lg:grid-cols-5'>
        <Kpi label={t('cvr.cost')} value={format(summary?.cost_to_date)} />
        <Kpi label={t('cvr.value')} value={format(summary?.value_to_date)} />
        <Kpi
          label={`${t('cvr.margin')}${summary?.margin_to_date_pct != null ? ` (${summary.margin_to_date_pct}%)` : ''}`}
          value={format(summary?.margin_to_date)}
          tone={tone(summary?.margin_to_date)}
        />
        <Kpi
          label={t('cvr.forecast_value')}
          value={format(summary?.forecast_value)}
        />
        <Kpi
          label={`${t('cvr.forecast_margin')}${summary?.forecast_margin_pct != null ? ` (${summary.forecast_margin_pct}%)` : ''}`}
          value={format(summary?.forecast_margin)}
          tone={tone(summary?.forecast_margin)}
        />
      </div>

      <div className='flex flex-wrap items-center gap-2'>
        {editable ? (
          <form
            className='flex flex-wrap items-center gap-2'
            onSubmit={(e) => {
              e.preventDefault()
              add.mutate(draft, {
                onSuccess: () => setDraft({ code: '', description: '' }),
              })
            }}
          >
            <Input
              className='h-8 w-24 font-mono'
              placeholder={t('cvr.code')}
              value={draft.code}
              onChange={(e) => setDraft({ ...draft, code: e.target.value })}
              required
            />
            <Input
              className='h-8 w-64'
              placeholder={t('cvr.head')}
              value={draft.description}
              onChange={(e) =>
                setDraft({ ...draft, description: e.target.value })
              }
              required
            />
            <Button size='sm' type='submit' disabled={add.isPending}>
              <Plus /> {t('cvr.add')}
            </Button>
          </form>
        ) : null}
        <Button
          size='sm'
          variant='outline'
          className='ms-auto'
          onClick={() =>
            grid.current?.api.exportDataAsCsv({
              fileName: `cvr-${projectId}.csv`,
            })
          }
        >
          <Download /> {t('common.export_csv')}
        </Button>
      </div>

      <div className='h-[420px]'>
        <DataGrid<CostHead>
          ref={grid}
          rowData={heads}
          columnDefs={columns}
          getRowId={(p) => String(p.data.id)}
          pinnedBottomRowData={totals}
          getRowClass={(p) =>
            p.node.rowPinned ? 'font-semibold bg-muted' : undefined
          }
          singleClickEdit
          onCellValueChanged={(e) => {
            if (
              !e.data ||
              e.node.rowPinned ||
              e.newValue === e.oldValue ||
              !e.colDef.field
            )
              return
            update.mutate({
              id: e.data.id,
              field: e.colDef.field,
              value: String(e.newValue),
            })
          }}
        />
      </div>

      <Card>
        <CardHeader>
          <CardTitle className='text-base'>{t('cvr.cashflow')}</CardTitle>
        </CardHeader>
        <CardContent>
          <CashflowChart periods={cashflow} currency={currency} />
        </CardContent>
      </Card>
    </>
  )
}

export default function CvrPage() {
  const { t } = useTranslation()
  const project = useCurrentProject()

  return (
    <Page
      title={t('cvr.title')}
      description={t('cvr.description')}
      projectScoped
    >
      {project ? (
        <Reconciliation
          key={project.id}
          projectId={project.id}
          currency={project.currency}
        />
      ) : (
        <p className='text-sm text-muted-foreground'>{t('cvr.no_project')}</p>
      )}
    </Page>
  )
}
