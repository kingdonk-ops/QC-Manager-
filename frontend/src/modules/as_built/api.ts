import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, unwrap } from '@/api/client'
import type { components } from '@/api/schema'
import { handleServerError } from '@/lib/handle-server-error'

type S = components['schemas']
export type AsBuilt = S['AsBuiltRead']
export type AsBuiltBody = S['AsBuiltCreate']
export type SurveyBody = S['AsBuiltSurvey']
export type VerifyBody = S['AsBuiltVerify']
export type SignBody = S['AsBuiltSign']

export const keys = {
  all: ['as_built'] as const,
  list: (projectId: number, status: string, tolerance: string) =>
    ['as_built', projectId, 'list', status, tolerance] as const,
}

export function useRecords(
  projectId: number,
  status: string,
  tolerance: string
) {
  return useQuery({
    queryKey: keys.list(projectId, status, tolerance),
    queryFn: async () =>
      (
        await unwrap(
          api.GET('/api/v1/as-built/', {
            params: {
              query: {
                project_id: projectId,
                items_per_page: 100,
                status: (status || undefined) as never,
                tolerance_result: (tolerance || undefined) as never,
              },
            },
          })
        )
      ).data as AsBuilt[],
  })
}

function useWrite<T>(call: (arg: T) => Promise<unknown>) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: call,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: keys.all })
      // Verifying an out-of-tolerance record can raise a non-conformance report.
      void qc.invalidateQueries({ queryKey: ['ncr'] })
    },
    onError: handleServerError,
  })
}

export function useCreateRecord() {
  return useWrite((body: AsBuiltBody) =>
    unwrap(api.POST('/api/v1/as-built/', { body }))
  )
}

const path = (id: number) => ({ params: { path: { record_id: id } } })

export function useSurvey(id: number) {
  return useWrite((body: SurveyBody) =>
    unwrap(api.POST('/api/v1/as-built/{record_id}/survey', { ...path(id), body }))
  )
}

export function useVerify(id: number) {
  return useWrite((body: VerifyBody) =>
    unwrap(api.POST('/api/v1/as-built/{record_id}/verify', { ...path(id), body }))
  )
}

export function useSignRecord(id: number) {
  return useWrite((body: SignBody) =>
    unwrap(api.POST('/api/v1/as-built/{record_id}/sign', { ...path(id), body }))
  )
}
