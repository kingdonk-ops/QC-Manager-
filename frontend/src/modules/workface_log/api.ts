import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, unwrap } from '@/api/client'
import type { components } from '@/api/schema'
import { handleServerError } from '@/lib/handle-server-error'

type S = components['schemas']
export type Log = S['LogRead']
export type LogUpdate = S['LogUpdate']
export type DaySummary = S['WorkfaceDaySummary']
export type Codes = S['WorkfaceCodes']

export const logKeys = {
  all: ['workface_log'] as const,
  day: (projectId: number, day: string) =>
    ['workface_log', 'day', projectId, day] as const,
  list: (projectId: number, day: string) =>
    ['workface_log', 'list', projectId, day] as const,
  one: (id: number) => ['workface_log', 'one', id] as const,
  codes: ['workface_log', 'codes'] as const,
}

export function useDaySummary(projectId: number, day: string) {
  return useQuery({
    queryKey: logKeys.day(projectId, day),
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/workface-log/day-summary', {
          params: { query: { project_id: projectId, work_date: day } },
        })
      ),
  })
}

export function useLogs(projectId: number, day: string) {
  return useQuery({
    queryKey: logKeys.list(projectId, day),
    queryFn: async () =>
      (
        await unwrap(
          api.GET('/api/v1/workface-log/logs/', {
            params: {
              query: {
                project_id: projectId,
                work_date: day,
                items_per_page: 100,
              },
            },
          })
        )
      ).data,
  })
}

export function useLog(id: number | null) {
  return useQuery({
    queryKey: logKeys.one(id ?? 0),
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/workface-log/logs/{log_id}', {
          params: { path: { log_id: id! } },
        })
      ),
    enabled: !!id,
  })
}

export function useCodes() {
  return useQuery({
    queryKey: logKeys.codes,
    queryFn: () => unwrap(api.GET('/api/v1/workface-log/codes')),
    staleTime: Infinity,
  })
}

export function useLogMutation<A, R>(fn: (args: A) => Promise<R>) {
  const qc = useQueryClient()
  const refresh = () => void qc.invalidateQueries({ queryKey: logKeys.all })
  return useMutation({
    mutationFn: fn,
    onSuccess: refresh,
    onError: handleServerError,
  })
}

export const logApi = {
  create: (body: S['LogCreate']) =>
    unwrap(api.POST('/api/v1/workface-log/logs/', { body })),
  save: ({ id, body }: { id: number; body: LogUpdate }) =>
    unwrap(
      api.PUT('/api/v1/workface-log/logs/{log_id}', {
        params: { path: { log_id: id } },
        body,
      })
    ),
  copyPrevious: (id: number) =>
    unwrap(
      api.POST('/api/v1/workface-log/logs/{log_id}/copy-previous', {
        params: { path: { log_id: id } },
      })
    ),
  step: ({
    id,
    step,
    note,
  }: {
    id: number
    step: 'submit' | 'sign' | 'return'
    note?: string | null
  }) => {
    const params = { path: { log_id: id } }
    const body = { note: note ?? null }
    if (step === 'submit')
      return unwrap(
        api.POST('/api/v1/workface-log/logs/{log_id}/submit', { params, body })
      )
    if (step === 'sign')
      return unwrap(
        api.POST('/api/v1/workface-log/logs/{log_id}/sign', { params, body })
      )
    return unwrap(
      api.POST('/api/v1/workface-log/logs/{log_id}/return', { params, body })
    )
  },
}
