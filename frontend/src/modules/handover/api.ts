import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, unwrap } from '@/api/client'
import type { components } from '@/api/schema'
import { handleServerError } from '@/lib/handle-server-error'

type S = components['schemas']
export type Handover = S['HandoverRead']
export type HandoverCreate = S['HandoverCreate']
export type HandoverUpdate = S['HandoverUpdate']
export type ItemIn = S['HandoverItemIn']

export const KINDS = [
  ['safety', 'Safety'],
  ['permit', 'Permits in force'],
  ['equipment', 'Equipment status'],
  ['wip', 'Work in progress'],
  ['open_item', 'Open items'],
  ['issue', 'Outstanding issues'],
] as const

export type Filter = 'all' | 'to' | 'from' | 'waiting'

const keys = {
  all: ['handover'] as const,
  list: (projectId: number, filter: Filter) =>
    ['handover', 'list', projectId, filter] as const,
  one: (id: number) => ['handover', 'one', id] as const,
  history: (id: number) => ['handover', 'history', id] as const,
  statuses: ['handover', 'statuses'] as const,
}

export function useHandovers(projectId: number, filter: Filter) {
  return useQuery({
    queryKey: keys.list(projectId, filter),
    queryFn: async () =>
      (
        await unwrap(
          api.GET('/api/v1/handover/handovers/', {
            params: {
              query: {
                project_id: projectId,
                mine: filter === 'to' || filter === 'from' ? filter : undefined,
                unacknowledged: filter === 'waiting' || undefined,
                items_per_page: 100,
              },
            },
          })
        )
      ).data,
  })
}

export function useHandover(id: number | null) {
  return useQuery({
    queryKey: keys.one(id ?? 0),
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/handover/handovers/{handover_id}', {
          params: { path: { handover_id: id! } },
        })
      ),
    enabled: !!id,
  })
}

export function useHandoverHistory(id: number) {
  return useQuery({
    queryKey: keys.history(id),
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/handover/handovers/{handover_id}/history', {
          params: { path: { handover_id: id } },
        })
      ) as Promise<{ to_status: string; changed_at: string; note?: string }[]>,
  })
}

export function useItemStatuses() {
  return useQuery({
    queryKey: keys.statuses,
    queryFn: () => unwrap(api.GET('/api/v1/handover/item-statuses')),
    staleTime: Infinity,
  })
}

export function useHandoverMutation<A, R>(fn: (args: A) => Promise<R>) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSuccess: () => void qc.invalidateQueries({ queryKey: keys.all }),
    onError: handleServerError,
  })
}

const path = (id: number) => ({ path: { handover_id: id } })

export const handoverApi = {
  create: (body: HandoverCreate) =>
    unwrap(api.POST('/api/v1/handover/handovers/', { body })),
  save: ({ id, body }: { id: number; body: HandoverUpdate }) =>
    unwrap(
      api.PUT('/api/v1/handover/handovers/{handover_id}', {
        params: path(id),
        body,
      })
    ),
  submit: (id: number) =>
    unwrap(
      api.POST('/api/v1/handover/handovers/{handover_id}/submit', {
        params: path(id),
      })
    ),
  recall: (id: number) =>
    unwrap(
      api.POST('/api/v1/handover/handovers/{handover_id}/recall', {
        params: path(id),
      })
    ),
  acknowledge: ({ id, note }: { id: number; note: string | null }) =>
    unwrap(
      api.POST('/api/v1/handover/handovers/{handover_id}/acknowledge', {
        params: path(id),
        body: { note },
      })
    ),
}
