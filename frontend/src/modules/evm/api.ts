import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, csrfHeaders, unwrap } from '@/api/client'
import type { components } from '@/api/schema'
import { handleServerError } from '@/lib/handle-server-error'

export type WorkPackage = components['schemas']['EvmWorkPackageRead']
export type WorkPackageCreate = components['schemas']['EvmWorkPackageCreate']
export type ProgressRow = components['schemas']['EvmProgressRow']
export type ProgressEntry = components['schemas']['EvmProgressEntry']
export type Metrics = components['schemas']['EvmMetricsValues']
export type MetricsRow = components['schemas']['EvmMetricsRow']
export type MetricsReport = components['schemas']['EvmMetricsReport']
export type SCurve = components['schemas']['EvmSCurve']
export type CurvePoint = components['schemas']['EvmCurvePoint']
export type Snapshot = components['schemas']['EvmSnapshotRead']
export type SnapshotCompare = components['schemas']['EvmSnapshotCompare']
export type Cashflow = components['schemas']['EvmCashflow']
export type EvmSettings = components['schemas']['EvmSettingsRead']
export type ImportReport = components['schemas']['EvmProgressImportReport']
export type FieldReport = components['schemas']['EvmFieldReport']

export type Basis = 'hours' | 'cost'
export type GroupBy = 'package' | 'account' | 'discipline' | 'project'
export type Interval = 'week' | 'month'
export type EacMethod = 'cpi' | 'budget_rate' | 'cpi_spi'
export type Curve = WorkPackage['curve']

const BASE = '/api/v1/evm'
const root = (projectId: number) => ['evm', projectId] as const
const at = (project_id: number) => ({ path: { project_id } })

export function useSettings(projectId: number) {
  return useQuery({
    queryKey: [...root(projectId), 'settings'],
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/evm/{project_id}/settings', {
          params: at(projectId),
        })
      ),
  })
}

export function useSetSettings(projectId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: { data_date: string | null; eac_method: EacMethod }) =>
      unwrap(
        api.PUT('/api/v1/evm/{project_id}/settings', {
          params: at(projectId),
          body,
        })
      ),
    onSuccess: () =>
      void queryClient.invalidateQueries({ queryKey: root(projectId) }),
    onError: handleServerError,
  })
}

export function useMetrics(
  projectId: number,
  date: string | undefined,
  basis: Basis,
  groupBy: GroupBy
) {
  return useQuery({
    queryKey: [...root(projectId), 'metrics', date, basis, groupBy],
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/evm/{project_id}/metrics', {
          params: {
            ...at(projectId),
            query: { date: date || undefined, basis, group_by: groupBy },
          },
        })
      ),
  })
}

export function useSCurve(
  projectId: number,
  date: string | undefined,
  basis: Basis,
  interval: Interval
) {
  return useQuery({
    queryKey: [...root(projectId), 's-curve', date, basis, interval],
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/evm/{project_id}/s-curve', {
          params: {
            ...at(projectId),
            query: { date: date || undefined, basis, interval },
          },
        })
      ),
  })
}

export function useCashflow(projectId: number) {
  return useQuery({
    queryKey: [...root(projectId), 'cashflow'],
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/evm/{project_id}/cashflow', {
          params: at(projectId),
        })
      ),
  })
}

export function useProgress(projectId: number, date: string | undefined) {
  return useQuery({
    queryKey: [...root(projectId), 'progress', date],
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/evm/{project_id}/progress', {
          params: { ...at(projectId), query: { date: date || undefined } },
        })
      ),
  })
}

export function useSaveProgress(projectId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: { data_date: string; entries: ProgressEntry[] }) =>
      unwrap(
        api.POST('/api/v1/evm/{project_id}/progress', {
          params: at(projectId),
          body: { ...body, set_data_date: true },
        })
      ),
    onSuccess: () =>
      void queryClient.invalidateQueries({ queryKey: root(projectId) }),
    onError: handleServerError,
  })
}

/** Actual hours from signed workface logs and % complete from verified progress, matched by WBS or P6 link. */
export function usePullFromField(projectId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (date: string) =>
      unwrap(
        api.POST('/api/v1/evm/{project_id}/progress/from-field', {
          params: { path: { project_id: projectId }, query: { date } },
        })
      ),
    onSuccess: () =>
      void queryClient.invalidateQueries({ queryKey: root(projectId) }),
    onError: handleServerError,
  })
}

/** Every package in the project, page by page. */
export function useWorkPackages(projectId: number) {
  return useQuery({
    queryKey: [...root(projectId), 'packages'],
    queryFn: async () => {
      const all: WorkPackage[] = []
      for (let page = 1; ; page++) {
        const res = await unwrap(
          api.GET('/api/v1/evm/work-packages/', {
            params: {
              query: { project_id: projectId, page, items_per_page: 100 },
            },
          })
        )
        all.push(...(res.data as WorkPackage[]))
        if (!res.has_more) return all
      }
    },
  })
}

function useRefresh(projectId: number) {
  const queryClient = useQueryClient()
  return () => void queryClient.invalidateQueries({ queryKey: root(projectId) })
}

export function useCreatePackage(projectId: number) {
  const refresh = useRefresh(projectId)
  return useMutation({
    mutationFn: (body: WorkPackageCreate) =>
      unwrap(api.POST('/api/v1/evm/work-packages/', { body })),
    onSuccess: refresh,
    onError: handleServerError,
  })
}

export function useUpdatePackage(projectId: number) {
  const refresh = useRefresh(projectId)
  return useMutation({
    mutationFn: ({
      id,
      field,
      value,
    }: {
      id: number
      field: string
      value: unknown
    }) =>
      unwrap(
        api.PATCH('/api/v1/evm/work-packages/{package_id}', {
          params: { path: { package_id: id } },
          body: { [field]: value } as never,
        })
      ),
    onSuccess: refresh,
    onError: (error) => {
      handleServerError(error)
      refresh()
    },
  })
}

export function useDeletePackage(projectId: number) {
  const refresh = useRefresh(projectId)
  return useMutation({
    mutationFn: (id: number) =>
      unwrap(
        api.DELETE('/api/v1/evm/work-packages/{package_id}', {
          params: { path: { package_id: id } },
        })
      ),
    onSuccess: refresh,
    onError: handleServerError,
  })
}

export function useSnapshots(projectId: number) {
  return useQuery({
    queryKey: [...root(projectId), 'snapshots'],
    queryFn: async () =>
      (
        await unwrap(
          api.GET('/api/v1/evm/{project_id}/snapshots/', {
            params: { ...at(projectId), query: { items_per_page: 100 } },
          })
        )
      ).data as Snapshot[],
  })
}

export function useCreateSnapshot(projectId: number) {
  const refresh = useRefresh(projectId)
  return useMutation({
    mutationFn: (body: { name: string; set_as_baseline: boolean }) =>
      unwrap(
        api.POST('/api/v1/evm/{project_id}/snapshots/', {
          params: at(projectId),
          body,
        })
      ),
    onSuccess: refresh,
    onError: handleServerError,
  })
}

export function useSetBaseline(projectId: number) {
  const refresh = useRefresh(projectId)
  return useMutation({
    mutationFn: ({ id, value }: { id: number; value: boolean }) =>
      unwrap(
        api.PATCH('/api/v1/evm/{project_id}/snapshots/{snapshot_id}', {
          params: { path: { project_id: projectId, snapshot_id: id } },
          body: { is_baseline: value },
        })
      ),
    onSuccess: refresh,
    onError: handleServerError,
  })
}

export function useDeleteSnapshot(projectId: number) {
  const refresh = useRefresh(projectId)
  return useMutation({
    mutationFn: (id: number) =>
      unwrap(
        api.DELETE('/api/v1/evm/{project_id}/snapshots/{snapshot_id}', {
          params: { path: { project_id: projectId, snapshot_id: id } },
        })
      ),
    onSuccess: refresh,
    onError: handleServerError,
  })
}

export function useCompare(
  projectId: number,
  snapshotId: number | null,
  date: string | undefined
) {
  return useQuery({
    queryKey: [...root(projectId), 'compare', snapshotId, date],
    enabled: snapshotId !== null,
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/evm/{project_id}/snapshots/{snapshot_id}/compare', {
          params: {
            path: { project_id: projectId, snapshot_id: snapshotId ?? 0 },
            query: { date: date || undefined },
          },
        })
      ),
  })
}

export async function importProgress(
  projectId: number,
  file: File,
  dataDate: string,
  dryRun: boolean
): Promise<ImportReport> {
  const form = new FormData()
  form.append('file', file)
  if (dataDate) form.append('data_date', dataDate)
  form.append('dry_run', String(dryRun))
  const response = await fetch(`${BASE}/${projectId}/import`, {
    method: 'POST',
    credentials: 'include',
    headers: csrfHeaders(),
    body: form,
  })
  const body = await response.json().catch(() => ({}))
  if (!response.ok)
    throw new Error(
      typeof body.detail === 'string' ? body.detail : 'Import failed'
    )
  return body as ImportReport
}

export function useInvalidateEvm(projectId: number) {
  return useRefresh(projectId)
}

export const reportUrl = (projectId: number, date: string, basis: Basis) =>
  `${BASE}/${projectId}/report.pdf?${new URLSearchParams({ ...(date ? { date } : {}), basis })}`

export const exportUrl = (projectId: number, date: string, basis: Basis) =>
  `${BASE}/${projectId}/export?${new URLSearchParams({ ...(date ? { date } : {}), basis, format: 'xlsx' })}`
