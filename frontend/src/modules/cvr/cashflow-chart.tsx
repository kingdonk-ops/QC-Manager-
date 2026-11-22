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
import type { CashflowPeriod } from './api'

function chartRows(periods: CashflowPeriod[]) {
  const rows = []
  const running = { planned: 0, actual: 0 }
  for (const p of periods) {
    running.planned += Number(p.planned_value)
    running.actual += Number(p.actual_value ?? 0)
    rows.push({
      month: new Date(p.period).toLocaleDateString(undefined, {
        month: 'short',
        year: '2-digit',
      }),
      planned_cost: Number(p.planned_cost),
      actual_cost: p.actual_cost === null ? null : Number(p.actual_cost),
      planned_value: running.planned,
      actual_value: p.actual_value === null ? null : running.actual,
    })
  }
  return rows
}

export function CashflowChart({
  periods,
  currency,
}: {
  periods: CashflowPeriod[]
  currency: string
}) {
  const { t } = useTranslation()
  const data = useMemo(() => chartRows(periods), [periods])
  const compact = new Intl.NumberFormat(undefined, {
    style: 'currency',
    currency,
    notation: 'compact',
    maximumFractionDigits: 1,
  })

  return (
    <ResponsiveContainer width='100%' height={260}>
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
          dataKey='month'
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
        <Tooltip formatter={(v) => compact.format(Number(v))} />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        <Bar
          dataKey='planned_cost'
          name={t('cvr.planned_cost')}
          fill='#cbd5e1'
          radius={[3, 3, 0, 0]}
        />
        <Bar
          dataKey='actual_cost'
          name={t('cvr.actual_cost')}
          fill='#64748b'
          radius={[3, 3, 0, 0]}
        />
        <Line
          dataKey='planned_value'
          name={t('cvr.planned_value')}
          stroke='#2563eb'
          strokeDasharray='5 4'
          dot={false}
        />
        <Line
          dataKey='actual_value'
          name={t('cvr.actual_value')}
          stroke='#16a34a'
          strokeWidth={2}
          dot={false}
          connectNulls={false}
        />
      </ComposedChart>
    </ResponsiveContainer>
  )
}
