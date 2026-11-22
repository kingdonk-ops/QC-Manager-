import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, unwrap } from '@/api/client'
import type { components } from '@/api/schema'
import { handleServerError } from '@/lib/handle-server-error'

export type ChangeOrder = components['schemas']['ChangeOrderRead']
export type ChangeOrderDetail = components['schemas']['ChangeOrderDetail']
export type ChangeOrderCreate = components['schemas']['ChangeOrderCreate']
export type ChangeOrderUpdate = components['schemas']['ChangeOrderUpdate']
export type Line = components['schemas']['CoLineRead']
export type ChangeLog = components['schemas']['ChangeLogSummary']

export const REASONS = [
  'client_request',
  'design_change',
  'unforeseen_condition',
  'regulatory',
  'error_omission',
  'other',
] as const
export const CVR_APPLY = ['none', 'value', 'cost', 'both'] as const

/** Next statuses the submitter may set; approvers set under_review, approved and rejected. */
export const SUBMITTER_MOVES: Record<string, string[]> = {
  draft: ['submitted', 'withdrawn'],
  submitted: ['withdrawn'],
  under_review: ['withdrawn'],
  rejected: ['draft'],
  withdrawn: ['draft'],
  approved: [],
}

const keys = {
  all: (projectId: number) => ['change_orders', projectId] as const,
  list: (projectId: number, status: string) =>
    ['change_orders', projectId, 'list', status] as const,
  summary: (projectId: number) =>
    ['change_orders', projectId, 'summary'] as const,
  one: (projectId: number, id: number) =>
    ['change_orders', projectId, 'one', id] as const,
}

export function useChangeOrders(projectId: number, status: string) {
  return useQuery({
    queryKey: keys.list(projectId, status),
    queryFn: async () =>
      (
        await unwrap(
          api.GET('/api/v1/change-orders/', {
            params: {
              query: {
                project_id: projectId,
                items_per_page: 100,
                status: status || undefined,
              },
            },
          })
        )
      ).data,
  })
}

export function useChangeLog(projectId: number) {
  return useQuery({
    queryKey: keys.summary(projectId),
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/change-orders/summary', {
          params: { query: { project_id: projectId } },
        })
      ),
  })
}

export function useChangeOrder(projectId: number, id: number | undefined) {
  return useQuery({
    queryKey: keys.one(projectId, id ?? 0),
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/change-orders/{co_id}', {
          params: { path: { co_id: id! } },
        })
      ),
    enabled: !!id,
  })
}

function useRefresh(projectId: number) {
  const queryClient = useQueryClient()
  return () =>
    void queryClient.invalidateQueries({ queryKey: keys.all(projectId) })
}

export function useCreateChangeOrder(projectId: number) {
  const refresh = useRefresh(projectId)
  return useMutation({
    mutationFn: (body: Omit<ChangeOrderCreate, 'project_id'>) =>
      unwrap(
        api.POST('/api/v1/change-orders/', {
          body: { ...body, project_id: projectId },
        })
      ),
    onSuccess: refresh,
    onError: handleServerError,
  })
}

export function useUpdateChangeOrder(projectId: number) {
  const refresh = useRefresh(projectId)
  return useMutation({
    mutationFn: ({ id, body }: { id: number; body: ChangeOrderUpdate }) =>
      unwrap(
        api.PATCH('/api/v1/change-orders/{co_id}', {
          params: { path: { co_id: id } },
          body,
        })
      ),
    onSuccess: refresh,
    onError: handleServerError,
  })
}

export function useMoveChangeOrder(projectId: number) {
  const refresh = useRefresh(projectId)
  return useMutation({
    mutationFn: ({
      id,
      status,
      comment,
    }: {
      id: number
      status: string
      comment?: string
    }) =>
      unwrap(
        api.PATCH('/api/v1/change-orders/{co_id}/status', {
          params: { path: { co_id: id } },
          body: { status: status as never, comment: comment || null },
        })
      ),
    onSuccess: refresh,
    onError: handleServerError,
  })
}

export function useDeleteChangeOrder(projectId: number) {
  const refresh = useRefresh(projectId)
  return useMutation({
    mutationFn: (id: number) =>
      unwrap(
        api.DELETE('/api/v1/change-orders/{co_id}', {
          params: { path: { co_id: id } },
        })
      ),
    onSuccess: refresh,
    onError: handleServerError,
  })
}

export function useLineMutations(projectId: number, coId: number) {
  const refresh = useRefresh(projectId)
  const add = useMutation({
    mutationFn: (body: { description: string }) =>
      unwrap(
        api.POST('/api/v1/change-orders/{co_id}/lines', {
          params: { path: { co_id: coId } },
          body: body as never,
        })
      ),
    onSuccess: refresh,
    onError: handleServerError,
  })
  const update = useMutation({
    mutationFn: ({
      id,
      field,
      value,
    }: {
      id: number
      field: string
      value: string | number | null
    }) =>
      unwrap(
        api.PATCH('/api/v1/change-orders/{co_id}/lines/{line_id}', {
          params: { path: { co_id: coId, line_id: id } },
          body: { [field]: value } as never,
        })
      ),
    onSuccess: refresh,
    onError: (error) => {
      handleServerError(error)
      refresh()
    },
  })
  const remove = useMutation({
    mutationFn: (id: number) =>
      unwrap(
        api.DELETE('/api/v1/change-orders/{co_id}/lines/{line_id}', {
          params: { path: { co_id: coId, line_id: id } },
        })
      ),
    onSuccess: refresh,
    onError: handleServerError,
  })
  return { add, update, remove }
}

/** The project's CVR cost heads, for linking lines; only fetched when the caller may read CVR. */
export function useCostHeadOptions(projectId: number, enabled: boolean) {
  return useQuery({
    queryKey: ['cvr', projectId, 'heads'],
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/cvr/projects/{project_id}/cost-heads', {
          params: { path: { project_id: projectId } },
        })
      ),
    enabled,
    retry: false,
  })
}

export const pdfUrl = (id: number) => `/api/v1/change-orders/${id}/pdf`
export const exportUrl = (projectId: number) =>
  `/api/v1/change-orders/export?project_id=${projectId}&format=xlsx`
