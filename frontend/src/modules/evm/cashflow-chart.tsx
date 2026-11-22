import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { Cashflow } from './api'

/** Monthly planned against actual cost from the packages, with CVR's cashflow beside it when present. */
export function CashflowChart({ cashflow }: { cashflow: Cashflow }) {
  const { t } = useTranslation()
  const compact = new Intl.NumberFormat(undefined, {
    style: 'currency',
    currency: cashflow.currency,
    notation: 'compact',
    maximumFractionDigits: 1,
  })
  const data = useMemo(
    () =>
      cashflow.months.map((m) => ({
        ...m,
        label: new Date(`${m.month}T00:00:00`).toLocaleDateString(undefined, {
          month: 'short',
          year: '2-digit',
        }),
      })),
    [cashflow.months]
  )

  if (!cashflow.cost_available && !cashflow.cvr_included)
    return (
      <p className='py-12 text-center text-sm text-muted-foreground'>
        {t('evm.no_cost')}
      </p>
    )

  return (
    <ResponsiveContainer width='100%' height={300}>
      <ComposedChart
        data={data}
        margin={{ top: 8, right: 8, bottom: 0, left: 8 }}
      >
        <CartesianGrid
          strokeDasharray='3 3'
          className='stroke-border'
          vertical={false}
        />
        <XAxis
          dataKey='label'
          tickLine={false}
          axisLine={false}
          fontSize={12}
        />
        <YAxis
          tickFormatter={(v) => compact.format(v)}
          tickLine={false}
          axisLine={false}
          fontSize={12}
          width={64}
        />
        <Tooltip
          formatter={(v) =>
            v === null || v === undefined ? '—' : compact.format(Number(v))
          }
        />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        <Bar
          dataKey='planned_cost'
          name={t('evm.planned_cost')}
          fill='#93c5fd'
          radius={[3, 3, 0, 0]}
        />
        <Bar
          dataKey='actual_cost'
          name={t('evm.actual_cost')}
          fill='#dc2626'
          fillOpacity={0.8}
          radius={[3, 3, 0, 0]}
        />
        {cashflow.cvr_included ? (
          <>
            <Bar
              dataKey='cvr_planned_cost'
              name={t('evm.cvr_planned')}
              fill='#cbd5e1'
              radius={[3, 3, 0, 0]}
            />
            <Bar
              dataKey='cvr_actual_cost'
              name={t('evm.cvr_actual')}
              fill='#64748b'
              radius={[3, 3, 0, 0]}
            />
          </>
        ) : null}
        <Line
          dataKey='cumulative_planned'
          name={t('evm.cumulative_planned')}
          stroke='#2563eb'
          strokeDasharray='5 4'
          dot={false}
        />
        <Line
          dataKey='cumulative_actual'
          name={t('evm.cumulative_actual')}
          stroke='#dc2626'
          strokeWidth={2}
          dot={false}
          connectNulls={false}
        />
      </ComposedChart>
    </ResponsiveContainer>
  )
}
