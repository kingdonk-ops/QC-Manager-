import type { PivotResult } from './api'

export type ChartType = 'bar' | 'line' | 'area' | 'pie' | 'stacked'

export const PALETTE = [
  '#2563eb',
  '#16a34a',
  '#f59e0b',
  '#dc2626',
  '#7c3aed',
  '#0891b2',
  '#db2777',
  '#65a30d',
  '#64748b',
  '#ea580c',
]

export function formatValue(
  value: number | null | undefined,
  unit: string,
  currency = 'AUD'
) {
  if (value === null || value === undefined) return '–'
  if (unit === 'money')
    return new Intl.NumberFormat(undefined, {
      style: 'currency',
      currency,
      notation: Math.abs(value) >= 1e6 ? 'compact' : 'standard',
      maximumFractionDigits: Math.abs(value) >= 1e6 ? 1 : 0,
    }).format(value)
  if (unit === '%') return `${value.toFixed(1)}%`
  if (unit === 'count') return value.toLocaleString()
  return `${value.toLocaleString(undefined, { maximumFractionDigits: 2 })}${unit ? ` ${unit}` : ''}`
}

export const keyLabel = (key: unknown[]) =>
  key.length
    ? key
        .map((v) => (v === null || v === undefined ? '(blank)' : String(v)))
        .join(' / ')
    : 'All'

/** A pivot result as Recharts rows: one row per row key, one series per column key (or per value). */
export function chartSeries(
  result: PivotResult,
  valueLabel: (field: string, agg: string) => string
) {
  const byColumn = result.column_fields.length > 0
  const series = byColumn
    ? result.column_keys.map((k, j) => ({ key: `s${j}`, name: keyLabel(k) }))
    : result.values.map((v, i) => ({
        key: `s${i}`,
        name: valueLabel(v.field, v.agg),
      }))
  const data = result.row_keys.map((rk, i) => {
    const row: Record<string, string | number | null> = { x: keyLabel(rk) }
    series.forEach((_, j) => {
      const cell = byColumn ? result.cells[i][j]?.[0] : result.cells[i][0]?.[j]
      row[`s${j}`] = cell ?? null
    })
    return row
  })
  return { data, series }
}

export const OPS = [
  'eq',
  'ne',
  'contains',
  'gt',
  'gte',
  'lt',
  'lte',
  'in',
] as const
export type Op = (typeof OPS)[number]
export type FilterRow = { field: string; op: Op; value: string }

/** Filter rows from the UI as the API's JSON filter object. */
export function toFilters(rows: FilterRow[]) {
  const out: Record<string, Record<string, unknown>> = {}
  for (const f of rows) {
    if (!f.field || f.value === '') continue
    const value =
      f.op === 'in'
        ? f.value.split(',').map((v) => v.trim())
        : f.value === 'true' || f.value === 'false'
          ? f.value === 'true'
          : f.value
    out[f.field] = { ...(out[f.field] ?? {}), [f.op]: value }
  }
  return out
}
