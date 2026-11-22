import { useMemo } from 'react'
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { Trends } from './api'

const COLOURS = [
  '#2563eb',
  '#16a34a',
  '#d97706',
  '#dc2626',
  '#7c3aed',
  '#0891b2',
  '#db2777',
  '#65a30d',
]

/** Monthly pass rate per trade or location, one line each. */
export function TrendChart({ trends }: { trends?: Trends }) {
  const { rows, series } = useMemo(() => {
    const groups = trends?.groups ?? []
    const months = new Set<string>()
    groups.forEach((g) => g.monthly.forEach((m) => months.add(m.month)))
    const rows = [...months].sort().map((month) => {
      const row: Record<string, string | number | null> = { month }
      for (const g of groups)
        row[g.key] = g.monthly.find((m) => m.month === month)?.pass_rate ?? null
      return row
    })
    return { rows, series: groups.map((g) => g.key) }
  }, [trends])

  if (!rows.length)
    return (
      <p className='text-sm text-muted-foreground'>
        No completed inspections yet.
      </p>
    )
  return (
    <ResponsiveContainer width='100%' height={240}>
      <LineChart data={rows} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
        <CartesianGrid strokeDasharray='3 3' className='stroke-border' />
        <XAxis dataKey='month' fontSize={12} />
        <YAxis domain={[0, 100]} unit='%' fontSize={12} width={44} />
        <Tooltip formatter={(v) => (v === null ? '—' : `${v}%`)} />
        <Legend />
        {series.map((key, i) => (
          <Line
            key={key}
            dataKey={key}
            stroke={COLOURS[i % COLOURS.length]}
            strokeWidth={2}
            connectNulls
            dot
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  )
}
