import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { cn } from '@/lib/utils'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import type { PivotResult } from './api'
import { type ChartType, PALETTE, keyLabel } from './lib'

const TONE: Record<string, string> = {
  good: 'text-green-600',
  warning: 'text-amber-600',
  bad: 'text-red-600',
  neutral: '',
}
const DOT: Record<string, string> = {
  good: 'bg-green-500',
  warning: 'bg-amber-500',
  bad: 'bg-red-500',
  neutral: 'bg-muted-foreground/40',
}

export function KpiCard({
  label,
  value,
  status = 'neutral',
  hint,
}: {
  label: string
  value: string
  status?: string
  hint?: string
}) {
  return (
    <Card className='gap-1 py-3' title={hint}>
      <CardHeader className='px-4'>
        <CardTitle className='flex items-center gap-2 text-xs font-medium text-muted-foreground'>
          <span
            className={cn('size-2 rounded-full', DOT[status] ?? DOT.neutral)}
            aria-hidden
          />
          {label}
        </CardTitle>
      </CardHeader>
      <CardContent className='px-4'>
        <p
          className={cn(
            'text-lg font-semibold tabular-nums',
            TONE[status] ?? ''
          )}
          data-status={status}
        >
          {value}
        </p>
      </CardContent>
    </Card>
  )
}

export function ChartView({
  type,
  data,
  series,
  height = 280,
}: {
  type: ChartType
  data: Record<string, string | number | null>[]
  series: { key: string; name: string }[]
  height?: number
}) {
  if (!data.length)
    return (
      <p className='py-10 text-center text-sm text-muted-foreground'>
        Nothing to chart.
      </p>
    )
  const axes = (
    <>
      <CartesianGrid
        strokeDasharray='3 3'
        className='stroke-border'
        vertical={false}
      />
      <XAxis dataKey='x' tickLine={false} axisLine={false} fontSize={12} />
      <YAxis
        tickLine={false}
        axisLine={false}
        fontSize={12}
        width={64}
        tickFormatter={(v) =>
          new Intl.NumberFormat(undefined, { notation: 'compact' }).format(v)
        }
      />
      <Tooltip />
      <Legend wrapperStyle={{ fontSize: 12 }} />
    </>
  )
  return (
    <ResponsiveContainer width='100%' height={height}>
      {type === 'pie' ? (
        <PieChart>
          <Tooltip />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <Pie
            data={data}
            dataKey={series[0]?.key ?? 's0'}
            nameKey='x'
            outerRadius='80%'
          >
            {data.map((_, i) => (
              <Cell key={i} fill={PALETTE[i % PALETTE.length]} />
            ))}
          </Pie>
        </PieChart>
      ) : type === 'line' ? (
        <LineChart data={data}>
          {axes}
          {series.map((s, i) => (
            <Line
              key={s.key}
              dataKey={s.key}
              name={s.name}
              stroke={PALETTE[i % PALETTE.length]}
              strokeWidth={2}
              dot={false}
            />
          ))}
        </LineChart>
      ) : type === 'area' ? (
        <AreaChart data={data}>
          {axes}
          {series.map((s, i) => (
            <Area
              key={s.key}
              dataKey={s.key}
              name={s.name}
              stroke={PALETTE[i % PALETTE.length]}
              fill={PALETTE[i % PALETTE.length]}
              fillOpacity={0.2}
              stackId='a'
            />
          ))}
        </AreaChart>
      ) : (
        <BarChart data={data}>
          {axes}
          {series.map((s, i) => (
            <Bar
              key={s.key}
              dataKey={s.key}
              name={s.name}
              fill={PALETTE[i % PALETTE.length]}
              stackId={type === 'stacked' ? 'a' : undefined}
              radius={type === 'stacked' ? 0 : [3, 3, 0, 0]}
            />
          ))}
        </BarChart>
      )}
    </ResponsiveContainer>
  )
}

/** The pivot as an HTML table with row and column totals. */
export function PivotTable({
  result,
  labels,
}: {
  result: PivotResult
  labels: Record<string, string>
}) {
  const valueName = (v: { field: string; agg: string }) =>
    `${v.field === '*' ? 'Rows' : (labels[v.field] ?? v.field)} (${v.agg})`
  const hasColumns = result.column_fields.length > 0
  const fmt = (n: number | null | undefined) =>
    n === null || n === undefined
      ? ''
      : n.toLocaleString(undefined, { maximumFractionDigits: 2 })
  return (
    <div className='overflow-auto rounded-md border'>
      <table className='w-full text-sm tabular-nums'>
        <thead className='bg-muted/60 text-xs'>
          <tr>
            {(result.row_fields.length ? result.row_fields : ['']).map((f) => (
              <th key={f} className='px-2 py-1.5 text-start font-semibold'>
                {labels[f] ?? f}
              </th>
            ))}
            {result.column_keys.map((ck, j) =>
              result.values.map((v, i) => (
                <th
                  key={`${j}-${i}`}
                  className='px-2 py-1.5 text-end font-semibold'
                >
                  {hasColumns ? `${keyLabel(ck)} · ` : ''}
                  {valueName(v)}
                </th>
              ))
            )}
            {hasColumns
              ? result.values.map((v, i) => (
                  <th
                    key={`t${i}`}
                    className='px-2 py-1.5 text-end font-semibold'
                  >
                    Total · {valueName(v)}
                  </th>
                ))
              : null}
          </tr>
        </thead>
        <tbody>
          {result.row_keys.map((rk, r) => (
            <tr key={r} className='border-t'>
              {(rk.length ? rk : ['All']).map((v, i) => (
                <td key={i} className='px-2 py-1'>
                  {v === null || v === undefined ? '(blank)' : String(v)}
                </td>
              ))}
              {result.cells[r].map((cell, j) =>
                cell.map((n, i) => (
                  <td key={`${j}-${i}`} className='px-2 py-1 text-end'>
                    {fmt(n)}
                  </td>
                ))
              )}
              {hasColumns
                ? result.row_totals[r].map((n, i) => (
                    <td
                      key={`t${i}`}
                      className='px-2 py-1 text-end font-medium'
                    >
                      {fmt(n)}
                    </td>
                  ))
                : null}
            </tr>
          ))}
          <tr className='border-t bg-muted/40 font-semibold'>
            <td
              className='px-2 py-1'
              colSpan={Math.max(1, result.row_fields.length)}
            >
              Total
            </td>
            {result.column_totals.map((col, j) =>
              col.map((n, i) => (
                <td key={`${j}-${i}`} className='px-2 py-1 text-end'>
                  {fmt(n)}
                </td>
              ))
            )}
            {hasColumns
              ? result.grand_total.map((n, i) => (
                  <td key={`g${i}`} className='px-2 py-1 text-end'>
                    {fmt(n)}
                  </td>
                ))
              : null}
          </tr>
        </tbody>
      </table>
      {result.truncated ? (
        <p className='p-2 text-xs text-muted-foreground'>
          Showing the first groups only; filter to see the rest.
        </p>
      ) : null}
    </div>
  )
}
