import { useMemo, useRef, useState } from 'react'
import type { ColDef, ValueFormatterParams } from 'ag-grid-community'
import type { AgGridReact } from 'ag-grid-react'
import { Download } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useProjectStore } from '@/stores/project-store'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { DataGrid } from '@/components/data-grid'
import { Page } from '@/components/layout/page'
import { StatusBadge } from '@/components/records/status-badge'
import {
  type PortfolioFilters,
  type PortfolioRow,
  usePortfolio,
  usePortfolioSummary,
} from './api'
import { KpiCard } from './charts'
import { formatValue } from './lib'

const ALL = 'all'

const moneyOf = (p: ValueFormatterParams<PortfolioRow>) =>
  p.value === null || p.value === undefined
    ? ''
    : formatValue(Number(p.value), 'money', p.data?.currency)

const pct = (p: ValueFormatterParams<PortfolioRow>) =>
  p.value === null || p.value === undefined
    ? ''
    : `${Number(p.value).toFixed(1)}%`

const signed = (v: unknown) =>
  cn(
    'tabular-nums',
    Number(v) < 0 ? 'text-red-600' : Number(v) > 0 ? 'text-green-600' : ''
  )

export default function PortfolioPage() {
  const { t } = useTranslation()
  const grid = useRef<AgGridReact<PortfolioRow>>(null)
  const [filters, setFilters] = useState<PortfolioFilters>({})
  const [search, setSearch] = useState('')
  const applied = useMemo(
    () => ({ ...filters, search: search.trim() || undefined }),
    [filters, search]
  )
  const { data } = usePortfolio(applied, 1)
  const { data: summary } = usePortfolioSummary(applied)
  const setProject = useProjectStore((s) => s.setProjectId)
  const rows = useMemo(() => data?.data ?? [], [data])

  const set = <K extends keyof PortfolioFilters>(key: K, value: string) =>
    setFilters((f) => ({
      ...f,
      [key]: value === ALL ? undefined : (value as PortfolioFilters[K]),
    }))

  const columns = useMemo<ColDef<PortfolioRow>[]>(() => {
    const money = (
      field: keyof PortfolioRow,
      headerName: string
    ): ColDef<PortfolioRow> => ({
      field,
      headerName,
      type: 'rightAligned',
      valueFormatter: moneyOf,
      cellClass: 'tabular-nums',
      width: 130,
    })
    const kpiColumns: ColDef<PortfolioRow>[] = (summary?.kpis ?? []).map(
      (k) => ({
        colId: `kpi-${k.key}`,
        headerName: String(k.label),
        type: 'rightAligned',
        width: 130,
        valueGetter: (p) => p.data?.kpis?.[String(k.key)] ?? null,
        valueFormatter: (p) =>
          p.value === null || p.value === undefined
            ? ''
            : formatValue(Number(p.value), String(k.unit), p.data?.currency),
        cellClass: (p) =>
          cn(
            'tabular-nums',
            {
              good: 'text-green-600',
              warning: 'text-amber-600',
              bad: 'text-red-600',
            }[p.data?.kpi_status?.[String(k.key)] ?? ''] ?? ''
          ),
      })
    )
    return [
      {
        field: 'code',
        headerName: t('reporting.project'),
        width: 110,
        pinned: 'left',
        cellClass: 'font-mono',
      },
      {
        field: 'name',
        headerName: t('reporting.name'),
        flex: 1,
        minWidth: 200,
      },
      { field: 'region', headerName: t('reporting.region'), width: 90 },
      {
        field: 'status',
        headerName: t('reporting.status'),
        width: 110,
        cellRenderer: (p: { value?: string }) => (
          <StatusBadge status={p.value} />
        ),
      },
      money('budget', t('reporting.budget')),
      money('value_to_date', t('reporting.value_to_date')),
      money('cost_to_date', t('reporting.cost_to_date')),
      {
        ...money('variance', t('reporting.variance')),
        cellClass: (p) => signed(p.value),
      },
      {
        field: 'variance_pct',
        headerName: t('reporting.variance_pct'),
        type: 'rightAligned',
        width: 110,
        valueFormatter: pct,
        cellClass: (p) => signed(p.value),
      },
      {
        field: 'forecast_margin_pct',
        headerName: t('reporting.forecast_margin'),
        type: 'rightAligned',
        width: 130,
        valueFormatter: pct,
        cellClass: (p) => signed(p.value),
      },
      {
        field: 'budget_status',
        headerName: t('reporting.budget_status'),
        width: 120,
        cellRenderer: (p: { value?: string }) =>
          p.value === 'none' ? null : (
            <StatusBadge
              status={p.value === 'over' ? 'over_budget' : 'on_track'}
            />
          ),
      },
      ...kpiColumns,
    ]
  }, [summary?.kpis, t])

  const main = summary?.totals[0]
  return (
    <Page
      title={t('reporting.portfolio')}
      description={t('reporting.portfolio_description')}
      actions={
        <Button
          size='sm'
          variant='outline'
          onClick={() =>
            grid.current?.api.exportDataAsCsv({ fileName: 'portfolio.csv' })
          }
        >
          <Download /> {t('common.export_csv')}
        </Button>
      }
    >
      <div className='grid grid-cols-2 gap-3 lg:grid-cols-5'>
        <KpiCard
          label={t('reporting.portfolio_value')}
          value={
            main
              ? formatValue(main.forecast_value, 'money', main.currency)
              : '–'
          }
          hint={summary?.totals
            .map(
              (c) =>
                `${c.currency}: ${formatValue(c.forecast_value, 'money', c.currency)}`
            )
            .join(' · ')}
        />
        <KpiCard
          label={t('reporting.portfolio_budget')}
          value={main ? formatValue(main.budget, 'money', main.currency) : '–'}
        />
        <KpiCard
          label={t('reporting.average_variance')}
          value={formatValue(summary?.average_variance_pct, '%')}
          status={
            summary?.average_variance_pct == null
              ? 'neutral'
              : summary.average_variance_pct < 0
                ? 'bad'
                : 'good'
          }
        />
        <KpiCard
          label={t('reporting.on_budget')}
          value={String(summary?.on_budget ?? '–')}
          status='good'
        />
        <KpiCard
          label={t('reporting.over_budget')}
          value={String(summary?.over_budget ?? '–')}
          status={summary?.over_budget ? 'bad' : 'neutral'}
        />
      </div>

      <div className='flex flex-wrap items-center gap-2'>
        <Input
          className='h-8 w-56'
          placeholder={t('reporting.search_projects')}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <Select
          value={filters.region ?? ALL}
          onValueChange={(v) => set('region', v)}
        >
          <SelectTrigger size='sm' className='h-8 w-36'>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>{t('reporting.all_regions')}</SelectItem>
            {(summary?.regions ?? []).map((r) => (
              <SelectItem key={r} value={r}>
                {r}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select
          value={filters.status ?? ALL}
          onValueChange={(v) => set('status', v)}
        >
          <SelectTrigger size='sm' className='h-8 w-36'>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>{t('reporting.all_statuses')}</SelectItem>
            <SelectItem value='active'>Active</SelectItem>
            <SelectItem value='on_hold'>On hold</SelectItem>
            <SelectItem value='closed'>Closed</SelectItem>
          </SelectContent>
        </Select>
        <Select
          value={filters.budget ?? ALL}
          onValueChange={(v) => set('budget', v)}
        >
          <SelectTrigger size='sm' className='h-8 w-40'>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>{t('reporting.any_budget')}</SelectItem>
            <SelectItem value='over'>{t('reporting.over_budget')}</SelectItem>
            <SelectItem value='on'>{t('reporting.on_budget')}</SelectItem>
            <SelectItem value='none'>{t('reporting.no_budget')}</SelectItem>
          </SelectContent>
        </Select>
        <span className='ms-auto text-sm text-muted-foreground'>
          {t('reporting.projects_count', { count: data?.total_count ?? 0 })}
        </span>
      </div>

      <div className='h-[520px]'>
        <DataGrid<PortfolioRow>
          ref={grid}
          rowData={rows}
          columnDefs={columns}
          getRowId={(p) => String(p.data.project_id)}
          onRowDoubleClicked={(e) => e.data && setProject(e.data.project_id)}
        />
      </div>
    </Page>
  )
}
