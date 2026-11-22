import type { ColumnState, GridApi } from 'ag-grid-community'
import { describe, expect, it } from 'vitest'
import { applyViewToGrid, gridViewState } from './use-saved-views'

/** Just enough of AG Grid's API to check what a view reads and writes. */
function fakeGrid(columns: string[], state: ColumnState[] = []) {
  const calls: Record<string, unknown> = {}
  const grid = {
    getColumns: () => columns.map((id) => ({ getColId: () => id })),
    getColumnState: () => state,
    getFilterModel: () => ({ status: { type: 'equals', filter: 'open' } }),
    getGridOption: () => 'pump',
    applyColumnState: (arg: unknown) => (calls.columns = arg),
    setFilterModel: (arg: unknown) => (calls.filters = arg),
    setGridOption: (key: string, value: unknown) => (calls[key] = value),
  }
  return { grid: grid as unknown as GridApi, calls }
}

describe('saved views on a grid', () => {
  it('reads the grid state a view keeps', () => {
    const { grid } = fakeGrid(
      [],
      [
        { colId: 'code', width: 90.4, sort: 'desc', sortIndex: 1 },
        { colId: 'title', flex: 1, sort: 'asc', sortIndex: 0 },
        { colId: 'status', hide: true, pinned: 'left' },
      ]
    )
    expect(gridViewState(grid)).toEqual({
      columns: [
        { colId: 'code', width: 90 },
        { colId: 'title', flex: 1 },
        { colId: 'status', hide: true, pinned: 'left' },
      ],
      sort: [
        { colId: 'title', sort: 'asc' },
        { colId: 'code', sort: 'desc' },
      ],
      filters: { status: { type: 'equals', filter: 'open' } },
      group_by: [],
      quick_search: 'pump',
    })
  })

  it('applies a view and skips columns the grid no longer has', () => {
    const { grid, calls } = fakeGrid(['code', 'title'])
    applyViewToGrid(grid, {
      columns: [
        { colId: 'gone', width: 50 },
        { colId: 'title', width: 200 },
      ],
      sort: [{ colId: 'code', sort: 'asc' }],
      filters: { gone: {}, title: { type: 'contains', filter: 'x' } },
      group_by: [],
      quick_search: null,
    })
    const applied = calls.columns as { state: ColumnState[] }
    expect(applied.state.map((c) => c.colId)).toEqual(['title', 'code'])
    expect(applied.state[1]).toMatchObject({ sort: 'asc', sortIndex: 0 })
    expect(calls.filters).toEqual({ title: { type: 'contains', filter: 'x' } })
    expect(calls.quickFilterText).toBe('')
  })
})
