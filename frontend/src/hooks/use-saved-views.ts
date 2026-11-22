/**
 * Saved register views for any `<DataGrid>`: columns (order, width, hidden, pinned), sort, filters,
 * quick search, personal or shared with the project or teams, with a default per register.
 *
 *   const views = useSavedViews('ncr.register', projectId)
 *   <SavedViewsMenu views={views} />
 *   <DataGrid onGridReady={views.onGridReady} ... />
 *
 * The caller's default view (else the project default) is applied when the grid is ready. A column a view
 * names that the grid no longer has is skipped. `group_by` is stored for registers that group rows
 * themselves (AG Grid Community has no row grouping): read it from `views.current?.config.group_by`.
 */
import { useCallback, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { ColumnState, GridApi, GridReadyEvent } from 'ag-grid-community'
import { toast } from 'sonner'
import { api, unwrap } from '@/api/client'
import type { components } from '@/api/schema'
import { handleServerError } from '@/lib/handle-server-error'
import { can, useSession } from '@/lib/session'

export type SavedView = components['schemas']['SavedViewRead']
export type ViewConfig = components['schemas']['SavedViewConfig']
export type Visibility = 'private' | 'project' | 'team'

/** The grid's current state, in the shape a view stores. */
export function gridViewState(grid: GridApi): ViewConfig {
  const state = grid.getColumnState()
  const sorted = state
    .filter((c) => c.sort)
    .sort((a, b) => (a.sortIndex ?? 0) - (b.sortIndex ?? 0))
  const quick = grid.getGridOption('quickFilterText')
  return {
    columns: state.map((c) => ({
      colId: c.colId,
      ...(c.width ? { width: Math.round(c.width) } : {}),
      ...(c.hide ? { hide: true } : {}),
      ...(c.pinned === 'left' || c.pinned === 'right'
        ? { pinned: c.pinned }
        : {}),
      ...(c.flex ? { flex: c.flex } : {}),
    })),
    sort: sorted.map((c) => ({
      colId: c.colId,
      sort: c.sort as 'asc' | 'desc',
    })),
    filters: grid.getFilterModel() ?? {},
    group_by: [],
    quick_search: quick || null,
  }
}

/** Put a view on the grid. Columns the grid doesn't have are skipped. */
export function applyViewToGrid(grid: GridApi, config: ViewConfig) {
  const known = new Set(
    (grid.getColumns() ?? []).map((c) => c.getColId() as string)
  )
  const sortIndex = new Map(
    (config.sort ?? []).map((s, i) => [s.colId, [s.sort, i] as const])
  )
  const state: ColumnState[] = (config.columns ?? [])
    .filter((c) => known.has(c.colId))
    .map((c) => ({
      colId: c.colId,
      width: c.width ?? undefined,
      hide: c.hide ?? false,
      pinned: c.pinned ?? null,
      flex: c.flex ?? undefined,
      sort: sortIndex.get(c.colId)?.[0] ?? null,
      sortIndex: sortIndex.get(c.colId)?.[1] ?? null,
    }))
  for (const [colId, [sort, i]] of sortIndex) {
    if (known.has(colId) && !state.some((c) => c.colId === colId))
      state.push({ colId, sort, sortIndex: i })
  }
  grid.applyColumnState({
    state,
    applyOrder: state.length > 0,
    defaultState: { sort: null },
  })
  const filters = Object.fromEntries(
    Object.entries(config.filters ?? {}).filter(([k]) => known.has(k))
  )
  grid.setFilterModel(Object.keys(filters).length ? filters : null)
  grid.setGridOption('quickFilterText', config.quick_search ?? '')
}

export function useSavedViews<T = unknown>(
  registerKey: string,
  projectId: number | null
) {
  const session = useSession()
  const qc = useQueryClient()
  const enabled = Boolean(projectId) && can(session, 'saved_views.read')
  const [grid, setGrid] = useState<GridApi | null>(null)
  const [current, setCurrent] = useState<SavedView | null>(null)

  const list = useQuery({
    queryKey: ['saved-views', projectId, registerKey, 'list'],
    enabled,
    retry: false,
    queryFn: async () =>
      (
        await unwrap(
          api.GET('/api/v1/saved-views/', {
            params: {
              query: {
                project_id: projectId ?? 0,
                register_key: registerKey,
                items_per_page: 100,
              },
            },
          })
        )
      ).data,
  })
  const apply = useCallback(
    (view: SavedView | null) => {
      if (!grid) return
      if (view) applyViewToGrid(grid, view.config as ViewConfig)
      else {
        grid.resetColumnState()
        grid.setFilterModel(null)
        grid.setGridOption('quickFilterText', '')
      }
      setCurrent(view)
    },
    [grid]
  )

  // The grid opens with the caller's default view (else the project default).
  const onGridReady = useCallback(
    (e: GridReadyEvent<T>) => {
      const ready = e.api as GridApi
      setGrid(ready)
      if (!enabled) return
      qc.fetchQuery({
        queryKey: ['saved-views', projectId, registerKey, 'default'],
        retry: false,
        queryFn: () =>
          unwrap(
            api.GET('/api/v1/saved-views/default', {
              params: {
                query: {
                  project_id: projectId ?? 0,
                  register_key: registerKey,
                },
              },
            })
          ),
      })
        .then((view) => {
          if (!view || ready.isDestroyed()) return
          applyViewToGrid(ready, view.config as ViewConfig)
          setCurrent(view)
        })
        .catch(() => undefined)
    },
    [enabled, qc, projectId, registerKey]
  )

  const refresh = () =>
    void qc.invalidateQueries({ queryKey: ['saved-views', projectId] })
  const save = useMutation({
    mutationFn: (body: {
      name: string
      visibility: Visibility
      team_ids: number[]
      is_default: boolean
    }) =>
      unwrap(
        api.POST('/api/v1/saved-views/', {
          body: {
            ...body,
            project_id: projectId ?? 0,
            register_key: registerKey,
            config: grid ? gridViewState(grid) : {},
          },
        })
      ),
    onSuccess: (view) => {
      setCurrent(view)
      toast.success(`View "${view.name}" saved`)
      refresh()
    },
    onError: handleServerError,
  })
  const update = useMutation({
    mutationFn: ({
      id,
      body,
    }: {
      id: number
      body: components['schemas']['SavedViewUpdate']
    }) =>
      unwrap(
        api.PATCH('/api/v1/saved-views/{view_id}', {
          params: { path: { view_id: id } },
          body,
        })
      ),
    onSuccess: (view) => {
      setCurrent((c) => (c?.id === view.id ? view : c))
      refresh()
    },
    onError: handleServerError,
  })
  const remove = useMutation({
    mutationFn: (id: number) =>
      unwrap(
        api.DELETE('/api/v1/saved-views/{view_id}', {
          params: { path: { view_id: id } },
        })
      ),
    onSuccess: (_, id) => {
      setCurrent((c) => (c?.id === id ? null : c))
      refresh()
    },
    onError: handleServerError,
  })

  /** Save the grid's current state into the current view. */
  const saveCurrent = () => {
    if (current && grid)
      update.mutate(
        { id: current.id, body: { config: gridViewState(grid) } },
        { onSuccess: () => toast.success(`View "${current.name}" updated`) }
      )
  }

  return {
    registerKey,
    enabled: enabled && !list.isError,
    views: list.data ?? [],
    current,
    onGridReady,
    apply,
    save,
    update,
    remove,
    saveCurrent,
  }
}

/** What the menu needs, whatever the grid's row type. */
export type SavedViews = Omit<ReturnType<typeof useSavedViews>, 'onGridReady'>
