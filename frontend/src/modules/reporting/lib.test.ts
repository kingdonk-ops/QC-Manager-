import { describe, expect, it } from 'vitest'
import type { PivotResult } from './api'
import { chartSeries, formatValue, toFilters } from './lib'

const result: PivotResult = {
  row_fields: ['status'],
  column_fields: ['priority'],
  values: [{ field: '*', agg: 'count' }],
  row_keys: [['done'], ['todo']],
  column_keys: [['high'], [null]],
  cells: [
    [[1], [null]],
    [[2], [1]],
  ],
  row_totals: [[1], [3]],
  column_totals: [[3], [1]],
  grand_total: [4],
  source_rows: 4,
  truncated: false,
}

describe('chartSeries', () => {
  it('makes one series per column key when the pivot has columns', () => {
    const { data, series } = chartSeries(result, (f) => f)
    expect(series).toEqual([
      { key: 's0', name: 'high' },
      { key: 's1', name: '(blank)' },
    ])
    expect(data).toEqual([
      { x: 'done', s0: 1, s1: null },
      { x: 'todo', s0: 2, s1: 1 },
    ])
  })

  it('makes one series per value without columns', () => {
    const flat: PivotResult = {
      ...result,
      column_fields: [],
      column_keys: [[]],
      values: [
        { field: 'budget', agg: 'sum' },
        { field: 'cost', agg: 'avg' },
      ],
      cells: [[[10, 2]], [[20, 4]]],
    }
    const { data, series } = chartSeries(flat, (f, agg) => `${f} ${agg}`)
    expect(series.map((s) => s.name)).toEqual(['budget sum', 'cost avg'])
    expect(data[1]).toEqual({ x: 'todo', s0: 20, s1: 4 })
  })
})

describe('toFilters', () => {
  it('builds the API filter object, merging operators on one column', () => {
    expect(
      toFilters([
        { field: 'status', op: 'in', value: 'todo, review' },
        { field: 'due', op: 'gte', value: '2026-01-01' },
        { field: 'due', op: 'lt', value: '2026-02-01' },
        { field: 'overdue', op: 'eq', value: 'true' },
        { field: 'title', op: 'contains', value: '' },
      ])
    ).toEqual({
      status: { in: ['todo', 'review'] },
      due: { gte: '2026-01-01', lt: '2026-02-01' },
      overdue: { eq: true },
    })
  })
})

describe('formatValue', () => {
  it('formats by unit', () => {
    expect(formatValue(null, '%')).toBe('–')
    expect(formatValue(12.345, '%')).toBe('12.3%')
    expect(formatValue(1500, 'count')).toBe((1500).toLocaleString())
  })
})
