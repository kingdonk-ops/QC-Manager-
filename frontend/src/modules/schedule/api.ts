import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { ApiError, api, csrfHeaders, unwrap } from '@/api/client'
import type { components } from '@/api/schema'
import { handleServerError } from '@/lib/handle-server-error'

export type Activity = components['schemas']['ScheduleActivityRead']
export type Dependency = components['schemas']['ScheduleDependencyRead']
export type Baseline = components['schemas']['ScheduleBaselineRead']
export type CalendarSettings = components['schemas']['ScheduleCalendarRead']
export type Gantt = components['schemas']['ScheduleGantt']
export type MonteCarloResult = components['schemas']['ScheduleMonteCarloResult']
export type ImportReport = components['schemas']['ScheduleImportReport']
export type LinkType = 'FS' | 'SS' | 'FF' | 'SF'
export type ActivityPatch = components['schemas']['ScheduleActivityUpdate']

const keys = {
  gantt: (projectId: number) => ['schedule', projectId, 'gantt'] as const,
}

/** Errors from the schedule: a dependency loop comes back as `{message, codes}`. */
export function scheduleError(error: unknown) {
  if (
    error instanceof ApiError &&
    error.detail &&
    typeof error.detail === 'object' &&
    'message' in error.detail
  ) {
    toast.error(String((error.detail as { message: unknown }).message))
    return
  }
  handleServerError(error)
}

export function useGantt(projectId: number) {
  return useQuery({
    queryKey: keys.gantt(projectId),
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/schedule/gantt/{project_id}', {
          params: { path: { project_id: projectId } },
        })
      ),
  })
}

function useRefresh(projectId: number) {
  const queryClient = useQueryClient()
  return () =>
    queryClient.invalidateQueries({ queryKey: keys.gantt(projectId) })
}

export function useUpdateActivity(projectId: number) {
  const refresh = useRefresh(projectId)
  return useMutation({
    mutationFn: ({ id, patch }: { id: number; patch: ActivityPatch }) =>
      unwrap(
        api.PATCH('/api/v1/schedule/activities/{activity_id}', {
          params: { path: { activity_id: id } },
          body: patch,
        })
      ),
    onSettled: refresh,
    onError: scheduleError,
  })
}

export type NewActivity = {
  name: string
  duration?: number
  type?: 'task' | 'milestone' | 'summary'
  parent_id?: number | null
  predecessor_id?: number | null
}

export function useAddActivity(projectId: number) {
  const refresh = useRefresh(projectId)
  return useMutation({
    mutationFn: (body: NewActivity) =>
      unwrap(
        api.POST('/api/v1/schedule/activities/', {
          body: { project_id: projectId, ...body } as never,
        })
      ),
    onSuccess: refresh,
    onError: scheduleError,
  })
}

export function useDeleteActivity(projectId: number) {
  const refresh = useRefresh(projectId)
  return useMutation({
    mutationFn: (id: number) =>
      unwrap(
        api.DELETE('/api/v1/schedule/activities/{activity_id}', {
          params: { path: { activity_id: id } },
        })
      ),
    onSuccess: refresh,
    onError: scheduleError,
  })
}

export function useAddDependency(projectId: number) {
  const refresh = useRefresh(projectId)
  return useMutation({
    mutationFn: (body: {
      predecessor_id: number
      successor_id: number
      type?: LinkType
      lag?: number
    }) => unwrap(api.POST('/api/v1/schedule/dependencies/', { body } as never)),
    onSuccess: refresh,
    onError: scheduleError,
  })
}

export function useDeleteDependency(projectId: number) {
  const refresh = useRefresh(projectId)
  return useMutation({
    mutationFn: (id: number) =>
      unwrap(
        api.DELETE('/api/v1/schedule/dependencies/{dependency_id}', {
          params: { path: { dependency_id: id } },
        })
      ),
    onSuccess: refresh,
    onError: scheduleError,
  })
}

export function useCalculate(projectId: number) {
  const refresh = useRefresh(projectId)
  return useMutation({
    mutationFn: () =>
      unwrap(
        api.POST('/api/v1/schedule/{project_id}/calculate', {
          params: { path: { project_id: projectId } },
        })
      ),
    onSuccess: refresh,
    onError: scheduleError,
  })
}

export function useSaveCalendar(projectId: number) {
  const refresh = useRefresh(projectId)
  return useMutation({
    mutationFn: (body: components['schemas']['ScheduleCalendarUpdate']) =>
      unwrap(
        api.PUT('/api/v1/schedule/{project_id}/calendar', {
          params: { path: { project_id: projectId } },
          body,
        })
      ),
    onSuccess: refresh,
    onError: scheduleError,
  })
}

export function useCreateBaseline(projectId: number) {
  const refresh = useRefresh(projectId)
  return useMutation({
    mutationFn: (body: { name: string; make_current: boolean }) =>
      unwrap(
        api.POST('/api/v1/schedule/{project_id}/baselines', {
          params: { path: { project_id: projectId } },
          body,
        })
      ),
    onSuccess: refresh,
    onError: scheduleError,
  })
}

export function useSetCurrentBaseline(projectId: number) {
  const refresh = useRefresh(projectId)
  return useMutation({
    mutationFn: (baselineId: number) =>
      unwrap(
        api.POST(
          '/api/v1/schedule/{project_id}/baselines/{baseline_id}/current',
          {
            params: {
              path: { project_id: projectId, baseline_id: baselineId },
            },
          }
        )
      ),
    onSuccess: refresh,
    onError: scheduleError,
  })
}

export function useDeleteBaseline(projectId: number) {
  const refresh = useRefresh(projectId)
  return useMutation({
    mutationFn: (baselineId: number) =>
      unwrap(
        api.DELETE('/api/v1/schedule/{project_id}/baselines/{baseline_id}', {
          params: { path: { project_id: projectId, baseline_id: baselineId } },
        })
      ),
    onSuccess: refresh,
    onError: scheduleError,
  })
}

export function useGenerate(projectId: number) {
  const refresh = useRefresh(projectId)
  return useMutation({
    mutationFn: (body: components['schemas']['ScheduleGenerateRequest']) =>
      unwrap(
        api.POST('/api/v1/schedule/{project_id}/generate', {
          params: { path: { project_id: projectId } },
          body,
        })
      ),
    onSuccess: refresh,
    onError: scheduleError,
  })
}

export function useMonteCarlo(projectId: number) {
  return useMutation({
    mutationFn: (body: components['schemas']['ScheduleMonteCarloRequest']) =>
      unwrap(
        api.POST('/api/v1/schedule/{project_id}/monte-carlo', {
          params: { path: { project_id: projectId } },
          body,
        })
      ),
    onError: scheduleError,
  })
}

/** Upload a P6 XER/XML or MS Project XML; `dryRun` only counts what is in it. */
export function useImport(projectId: number) {
  const refresh = useRefresh(projectId)
  return useMutation({
    mutationFn: async ({
      file,
      dryRun,
      replace,
    }: {
      file: File
      dryRun: boolean
      replace: boolean
    }): Promise<ImportReport> => {
      const form = new FormData()
      form.append('file', file)
      form.append('dry_run', String(dryRun))
      form.append('replace', String(replace))
      const response = await fetch(`/api/v1/schedule/${projectId}/import`, {
        method: 'POST',
        credentials: 'include',
        headers: csrfHeaders(),
        body: form,
      })
      const body = await response.json().catch(() => ({}))
      if (!response.ok) throw new ApiError(response.status, body.detail)
      return body as ImportReport
    },
    onSuccess: (report) => {
      if (!report.dry_run) void refresh()
    },
    onError: scheduleError,
  })
}

export function exportUrl(
  projectId: number,
  format: 'msp_xml' | 'xlsx' | 'csv'
) {
  return `/api/v1/schedule/${projectId}/export?format=${format}`
}
