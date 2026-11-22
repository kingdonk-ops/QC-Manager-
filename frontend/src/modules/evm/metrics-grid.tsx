import { useMemo } from 'react'
import type { CellClassParams, ColDef } from 'ag-grid-community'
import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'
import { DataGrid } from '@/components/data-grid'
import type { Basis, Metrics, MetricsRow } from './api'
import {
  forecastTone,
  formatAmount,
  formatIndex,
  indexTone,
  tcpiTone,
  toneText,
} from './thresholds'

const toned =
  (tone: (row: MetricsRow) => ReturnType<typeof indexTone>) =>
  (p: CellClassParams<MetricsRow>) =>
    cn('font-medium tabular-nums', p.data && toneText[tone(p.data)])

const signed = (p: CellClassParams<MetricsRow>) =>
  cn(
    'tabular-nums',
    Number(p.value) < 0
      ? 'text-red-600'
      : Number(p.value) > 0 && 'text-green-600'
  )

/** One row per package, control account or discipline, with the totals pinned below. */
export function MetricsGrid({
  rows,
  total,
  basis,
  currency,
  groupLabel,
}: {
  rows: MetricsRow[]
  total: Metrics
  basis: Basis
  currency: string
  groupLabel: string
}) {
  const { t } = useTranslation()
  const columns = useMemo<ColDef<MetricsRow>[]>(() => {
    const amount = (
      field: keyof Metrics,
      headerName: string,
      extra: Partial<ColDef<MetricsRow>> = {}
    ): ColDef<MetricsRow> => ({
      field,
      headerName,
      type: 'rightAligned',
      width: 110,
      valueFormatter: (p) => formatAmount(p.value, basis, currency),
      cellClass: 'tabular-nums',
      ...extra,
    })
    const index = (
      field: keyof Metrics,
      headerName: string,
      cellClass: ColDef<MetricsRow>['cellClass']
    ): ColDef<MetricsRow> => ({
      field,
      headerName,
      type: 'rightAligned',
      width: 84,
      valueFormatter: (p) => formatIndex(p.value),
      cellClass,
    })
    return [
      {
        field: 'label',
        headerName: groupLabel,
        pinned: 'left',
        minWidth: 220,
        flex: 1,
      },
      amount('bac', t('evm.bac')),
      amount('pv', t('evm.pv')),
      amount('ev', t('evm.ev')),
      amount('ac', t('evm.ac')),
      amount('sv', t('evm.sv'), { cellClass: signed }),
      amount('cv', t('evm.cv'), { cellClass: signed }),
      index(
        'spi',
        t('evm.spi'),
        toned((r) => indexTone(r.spi))
      ),
      index(
        'cpi',
        t('evm.cpi'),
        toned((r) => indexTone(r.cpi))
      ),
      amount('eac', t('evm.eac'), {
        cellClass: toned((r) => forecastTone(r.bac, r.eac)),
      }),
      amount('etc', t('evm.etc')),
      amount('vac', t('evm.vac'), { cellClass: signed }),
      index(
        'tcpi',
        t('evm.tcpi'),
        toned((r) => tcpiTone(r.tcpi))
      ),
      {
        field: 'percent_complete',
        headerName: t('evm.percent_complete'),
        type: 'rightAligned',
        width: 96,
        valueFormatter: (p) =>
          p.value === null || p.value === undefined
            ? '—'
            : `${Number(p.value).toFixed(1)}%`,
      },
      index('productivity', t('evm.productivity'), 'tabular-nums'),
    ]
  }, [basis, currency, groupLabel, t])

  const pinned = useMemo(
    () => [
      {
        ...total,
        key: '__total',
        label: t('common.total'),
        packages: rows.length,
      } as MetricsRow,
    ],
    [rows.length, t, total]
  )

  return (
    <div className='h-[420px]'>
      <DataGrid<MetricsRow>
        rowData={rows}
        columnDefs={columns}
        getRowId={(p) => p.data.key}
        pinnedBottomRowData={pinned}
        getRowClass={(p) =>
          p.node.rowPinned ? 'font-semibold bg-muted' : undefined
        }
      />
    </div>
  )
}
