import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { ApiError, api, csrfHeaders, unwrap } from '@/api/client'
import type { components } from '@/api/schema'
import { handleServerError } from '@/lib/handle-server-error'

type S = components['schemas']
export type DatasetInfo = S['DatasetInfo']
export type ColumnInfo = S['ColumnInfo']
export type KpiInfo = S['KpiInfo']
export type KpiValue = S['KpiValue']
export type PortfolioRow = S['PortfolioRow']
export type PortfolioSummary = S['PortfolioSummary']
export type PivotResult = S['PivotResult']
export type Template = S['TemplateRead']
export type TemplateIn = S['TemplateIn']
export type Section = Template['sections'][number]
export type Schedule = S['ScheduleRead']
export type ScheduleIn = S['ScheduleIn']
export type Run = S['RunRead']
export type Agg = 'sum' | 'avg' | 'count' | 'min' | 'max'
export type PivotValue = { field: string; agg: Agg }
export type PivotRequest = {
  dataset: string
  project_id?: number | null
  rows: string[]
  columns: string[]
  values: PivotValue[]
  filters: Record<string, unknown>
}
export type PortfolioFilters = {
  region?: string
  status?: 'active' | 'on_hold' | 'closed'
  budget?: 'over' | 'on' | 'none'
  search?: string
}

export const reportingKeys = {
  all: ['reporting'] as const,
  datasets: (projectId?: number) =>
    ['reporting', 'datasets', projectId ?? null] as const,
  kpis: (projectId: number) => ['reporting', 'kpi', projectId] as const,
  kpiDefs: ['reporting', 'kpi-defs'] as const,
  portfolio: (filters: PortfolioFilters, page: number) =>
    ['reporting', 'portfolio', filters, page] as const,
  summary: (filters: PortfolioFilters) =>
    ['reporting', 'portfolio-summary', filters] as const,
  pivot: (request: PivotRequest | null) =>
    ['reporting', 'pivot', request] as const,
  templates: ['reporting', 'templates'] as const,
  schedules: ['reporting', 'schedules'] as const,
  runs: (id: number) => ['reporting', 'runs', id] as const,
}

export function useDatasets(projectId?: number) {
  return useQuery({
    queryKey: reportingKeys.datasets(projectId),
    queryFn: async () =>
      (
        await unwrap(
          api.GET('/api/v1/reporting/datasets/', {
            params: {
              query: { project_id: projectId, items_per_page: 100 },
            },
          })
        )
      ).data,
  })
}

export function useKpiDefinitions() {
  return useQuery({
    queryKey: reportingKeys.kpiDefs,
    queryFn: async () =>
      (
        await unwrap(
          api.GET('/api/v1/reporting/kpis/', {
            params: { query: { items_per_page: 100 } },
          })
        )
      ).data,
  })
}

export function useProjectKpis(projectId: number) {
  return useQuery({
    queryKey: reportingKeys.kpis(projectId),
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/reporting/kpi/{project_id}', {
          params: { path: { project_id: projectId } },
        })
      ),
  })
}

export function usePortfolio(filters: PortfolioFilters, page: number) {
  return useQuery({
    queryKey: reportingKeys.portfolio(filters, page),
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/reporting/portfolio/', {
          params: { query: { ...filters, page, items_per_page: 100 } },
        })
      ),
  })
}

export function usePortfolioSummary(filters: PortfolioFilters) {
  return useQuery({
    queryKey: reportingKeys.summary(filters),
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/reporting/portfolio/summary', {
          params: { query: filters },
        })
      ),
  })
}

export function usePivot(request: PivotRequest | null) {
  return useQuery({
    queryKey: reportingKeys.pivot(request),
    enabled: request !== null,
    queryFn: () =>
      unwrap(
        api.POST('/api/v1/reporting/pivot', {
          body: request as never,
        })
      ),
    retry: false,
  })
}

export function useTemplates() {
  return useQuery({
    queryKey: reportingKeys.templates,
    queryFn: async () =>
      (
        await unwrap(
          api.GET('/api/v1/reporting/templates/', {
            params: { query: { items_per_page: 100 } },
          })
        )
      ).data,
  })
}

export function useSaveTemplate() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, body }: { id?: number; body: TemplateIn }) =>
      id
        ? unwrap(
            api.PUT('/api/v1/reporting/templates/{template_id}', {
              params: { path: { template_id: id } },
              body,
            })
          )
        : unwrap(api.POST('/api/v1/reporting/templates/', { body })),
    onSuccess: () => {
      toast.success('Template saved')
      void queryClient.invalidateQueries({ queryKey: reportingKeys.templates })
    },
    onError: handleServerError,
  })
}

export function useCopyTemplate() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) =>
      unwrap(
        api.POST('/api/v1/reporting/templates/{template_id}/copy', {
          params: { path: { template_id: id } },
        })
      ),
    onSuccess: () =>
      void queryClient.invalidateQueries({ queryKey: reportingKeys.templates }),
    onError: handleServerError,
  })
}

export function useDeleteTemplate() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) =>
      unwrap(
        api.DELETE('/api/v1/reporting/templates/{template_id}', {
          params: { path: { template_id: id } },
        })
      ),
    onSuccess: () =>
      void queryClient.invalidateQueries({ queryKey: reportingKeys.templates }),
    onError: handleServerError,
  })
}

export function useSchedules() {
  return useQuery({
    queryKey: reportingKeys.schedules,
    queryFn: async () =>
      (
        await unwrap(
          api.GET('/api/v1/reporting/schedules/', {
            params: { query: { items_per_page: 100 } },
          })
        )
      ).data,
  })
}

export function useRuns(scheduleId: number) {
  return useQuery({
    queryKey: reportingKeys.runs(scheduleId),
    queryFn: async () =>
      (
        await unwrap(
          api.GET('/api/v1/reporting/schedules/{schedule_id}/runs/', {
            params: {
              path: { schedule_id: scheduleId },
              query: { items_per_page: 20 },
            },
          })
        )
      ).data,
  })
}

export function useSaveSchedule() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, body }: { id?: number; body: ScheduleIn }) =>
      id
        ? unwrap(
            api.PUT('/api/v1/reporting/schedules/{schedule_id}', {
              params: { path: { schedule_id: id } },
              body,
            })
          )
        : unwrap(api.POST('/api/v1/reporting/schedules/', { body })),
    onSuccess: () => {
      toast.success('Schedule saved')
      void queryClient.invalidateQueries({ queryKey: reportingKeys.schedules })
    },
    onError: handleServerError,
  })
}

export function useDeleteSchedule() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) =>
      unwrap(
        api.DELETE('/api/v1/reporting/schedules/{schedule_id}', {
          params: { path: { schedule_id: id } },
        })
      ),
    onSuccess: () =>
      void queryClient.invalidateQueries({ queryKey: reportingKeys.schedules }),
    onError: handleServerError,
  })
}

export function useSendNow() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) =>
      unwrap(
        api.POST('/api/v1/reporting/schedules/{schedule_id}/send', {
          params: { path: { schedule_id: id } },
        })
      ),
    onSuccess: (runs, id) => {
      const failed = runs.filter((r) => r.status !== 'success')
      if (failed.length) toast.error(failed[0].message ?? 'Sending failed')
      else toast.success(`Sent ${runs.length} report(s)`)
      void queryClient.invalidateQueries({ queryKey: reportingKeys.schedules })
      void queryClient.invalidateQueries({ queryKey: reportingKeys.runs(id) })
    },
    onError: handleServerError,
  })
}

function filenameOf(response: Response, fallback: string) {
  const header = response.headers.get('content-disposition') ?? ''
  return /filename="([^"]+)"/.exec(header)?.[1] ?? fallback
}

/** POSTs (or GETs, without a body) and saves the file the server answers with. */
export async function download(url: string, body?: unknown, fallback = 'file') {
  const response = await fetch(url, {
    method: body === undefined ? 'GET' : 'POST',
    credentials: 'include',
    headers:
      body === undefined
        ? {}
        : { 'Content-Type': 'application/json', ...csrfHeaders() },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (!response.ok) {
    let detail: unknown = response.statusText
    try {
      detail = (await response.json()).detail
    } catch {
      /* not JSON */
    }
    throw new ApiError(response.status, detail)
  }
  const blob = await response.blob()
  const link = document.createElement('a')
  link.href = URL.createObjectURL(blob)
  link.download = filenameOf(response, fallback)
  document.body.appendChild(link)
  link.click()
  link.remove()
  setTimeout(() => URL.revokeObjectURL(link.href), 1000)
}

export function useDownload() {
  return useMutation({
    mutationFn: ({ url, body }: { url: string; body?: unknown }) =>
      download(url, body),
    onError: handleServerError,
  })
}
