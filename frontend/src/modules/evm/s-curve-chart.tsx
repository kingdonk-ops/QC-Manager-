import { useTranslation } from 'react-i18next'
import {
  Bar,
  BarChart,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { Basis, SCurve } from './api'
import { formatAmount } from './thresholds'

const COLORS = {
  pv: '#2563eb',
  ev: '#16a34a',
  ac: '#dc2626',
  forecast: '#f59e0b',
  baseline: '#94a3b8',
}

function useAxis(basis: Basis, currency: string) {
  const compact = new Intl.NumberFormat(undefined, {
    notation: 'compact',
    maximumFractionDigits: 1,
    ...(basis === 'cost' ? { style: 'currency', currency } : {}),
  })
  return {
    tick: (v: number) => compact.format(v),
    tooltip: (v: unknown) =>
      v === null || v === undefined
        ? '—'
        : formatAmount(Number(v), basis, currency),
  }
}

/** Cumulative PV, EV and AC, the forecast to EAC, and the baseline's PV when there is one. */
export function SCurveChart({
  curve,
  basis,
  currency,
}: {
  curve: SCurve
  basis: Basis
  currency: string
}) {
  const { t } = useTranslation()
  const axis = useAxis(basis, currency)
  const dataDateLabel = curve.points.find(
    (p) => p.period_start <= curve.data_date && curve.data_date <= p.period_end
  )?.label
  const hasBaseline = curve.points.some((p) => p.baseline_pv !== null)

  if (!curve.points.length)
    return (
      <p className='py-12 text-center text-sm text-muted-foreground'>
        {t('evm.no_curve')}
      </p>
    )

  return (
    <ResponsiveContainer width='100%' height={320}>
      <ComposedChart
        data={curve.points}
        margin={{ top: 8, right: 16, bottom: 0, left: 8 }}
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
          minTickGap={16}
        />
        <YAxis
          tickFormatter={axis.tick}
          tickLine={false}
          axisLine={false}
          fontSize={12}
          width={64}
        />
        <Tooltip formatter={axis.tooltip} />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        {dataDateLabel ? (
          <ReferenceLine
            x={dataDateLabel}
            stroke='#64748b'
            strokeDasharray='2 2'
            label={{
              value: t('evm.data_date'),
              position: 'insideTopLeft',
              fontSize: 11,
            }}
          />
        ) : null}
        {curve.eac !== null ? (
          <ReferenceLine
            y={curve.eac}
            stroke={COLORS.forecast}
            strokeDasharray='4 4'
            strokeOpacity={0.6}
          />
        ) : null}
        {hasBaseline ? (
          <Line
            dataKey='baseline_pv'
            name={t('evm.baseline_pv')}
            stroke={COLORS.baseline}
            strokeDasharray='6 3'
            dot={false}
          />
        ) : null}
        <Line
          dataKey='pv'
          name={t('evm.pv')}
          stroke={COLORS.pv}
          strokeWidth={2}
          dot={false}
        />
        <Line
          dataKey='ev'
          name={t('evm.ev')}
          stroke={COLORS.ev}
          strokeWidth={2}
          dot={false}
          connectNulls={false}
        />
        <Line
          dataKey='ac'
          name={t('evm.ac')}
          stroke={COLORS.ac}
          strokeWidth={2}
          dot={false}
          connectNulls={false}
        />
        <Line
          dataKey='forecast'
          name={t('evm.forecast')}
          stroke={COLORS.forecast}
          strokeWidth={2}
          strokeDasharray='5 4'
          dot={false}
          connectNulls={false}
        />
      </ComposedChart>
    </ResponsiveContainer>
  )
}

/** Planned, earned and actual per period: the histogram beside the S-curve. */
export function PeriodChart({
  curve,
  basis,
  currency,
}: {
  curve: SCurve
  basis: Basis
  currency: string
}) {
  const { t } = useTranslation()
  const axis = useAxis(basis, currency)
  return (
    <ResponsiveContainer width='100%' height={220}>
      <BarChart
        data={curve.points}
        margin={{ top: 8, right: 16, bottom: 0, left: 8 }}
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
          minTickGap={16}
        />
        <YAxis
          tickFormatter={axis.tick}
          tickLine={false}
          axisLine={false}
          fontSize={12}
          width={64}
        />
        <Tooltip formatter={axis.tooltip} />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        <Bar
          dataKey='period_pv'
          name={t('evm.pv')}
          fill={COLORS.pv}
          fillOpacity={0.35}
          radius={[3, 3, 0, 0]}
        />
        <Bar
          dataKey='period_ev'
          name={t('evm.ev')}
          fill={COLORS.ev}
          radius={[3, 3, 0, 0]}
        />
        <Bar
          dataKey='period_ac'
          name={t('evm.ac')}
          fill={COLORS.ac}
          fillOpacity={0.8}
          radius={[3, 3, 0, 0]}
        />
      </BarChart>
    </ResponsiveContainer>
  )
}
