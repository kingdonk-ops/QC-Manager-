import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, unwrap } from '@/api/client'
import type { components } from '@/api/schema'
import { handleServerError } from '@/lib/handle-server-error'

export type CostHead = components['schemas']['CostHeadRead']
export type Summary = components['schemas']['CvrSummary']
export type CashflowPeriod = components['schemas']['CashflowPeriodRead']

const keys = {
  heads: (projectId: number) => ['cvr', projectId, 'heads'] as const,
  summary: (projectId: number) => ['cvr', projectId, 'summary'] as const,
  cashflow: (projectId: number) => ['cvr', projectId, 'cashflow'] as const,
}

const path = { params: { path: { project_id: 0 } } }
const at = (project_id: number) => ({
  params: { path: { ...path.params.path, project_id } },
})

export function useCostHeads(projectId: number) {
  return useQuery({
    queryKey: keys.heads(projectId),
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/cvr/projects/{project_id}/cost-heads', at(projectId))
      ),
  })
}

export function useSummary(projectId: number) {
  return useQuery({
    queryKey: keys.summary(projectId),
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/cvr/projects/{project_id}/summary', at(projectId))
      ),
  })
}

export function useCashflow(projectId: number) {
  return useQuery({
    queryKey: keys.cashflow(projectId),
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/cvr/projects/{project_id}/cashflow', at(projectId))
      ),
  })
}

function useRefresh(projectId: number) {
  const queryClient = useQueryClient()
  return () => {
    void queryClient.invalidateQueries({ queryKey: keys.heads(projectId) })
    void queryClient.invalidateQueries({ queryKey: keys.summary(projectId) })
  }
}

/** One cell edit. The grid already shows the new value; a failure reloads the server's. */
export function useUpdateCostHead(projectId: number) {
  const refresh = useRefresh(projectId)
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({
      id,
      field,
      value,
    }: {
      id: number
      field: string
      value: string
    }) =>
      unwrap(
        api.PATCH('/api/v1/cvr/projects/{project_id}/cost-heads/{head_id}', {
          params: { path: { project_id: projectId, head_id: id } },
          body: { [field]: value } as never,
        })
      ),
    onSuccess: () =>
      void queryClient.invalidateQueries({ queryKey: keys.summary(projectId) }),
    onError: (error) => {
      handleServerError(error)
      refresh()
    },
  })
}

export function useAddCostHead(projectId: number) {
  const refresh = useRefresh(projectId)
  return useMutation({
    mutationFn: (body: { code: string; description: string }) =>
      unwrap(
        api.POST('/api/v1/cvr/projects/{project_id}/cost-heads', {
          ...at(projectId),
          body: body as never,
        })
      ),
    onSuccess: refresh,
    onError: handleServerError,
  })
}

export function useDeleteCostHead(projectId: number) {
  const refresh = useRefresh(projectId)
  return useMutation({
    mutationFn: (id: number) =>
      unwrap(
        api.DELETE('/api/v1/cvr/projects/{project_id}/cost-heads/{head_id}', {
          params: { path: { project_id: projectId, head_id: id } },
        })
      ),
    onSuccess: refresh,
    onError: handleServerError,
  })
}
