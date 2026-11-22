import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, unwrap } from '@/api/client'
import type { components } from '@/api/schema'
import { handleServerError } from '@/lib/handle-server-error'

type S = components['schemas']
export type Ncr = S['NcrRead']
export type NcrAction = S['NcrActionRead']
export type NcrCreate = S['NcrCreate']
export type NcrUpdate = S['NcrUpdate']
export type NcrActionCreate = S['NcrActionCreate']
export type NcrActionUpdate = S['NcrActionUpdate']

export const LIFECYCLE = [
  'open',
  'under_investigation',
  'corrective_action_planned',
  'corrective_action_taken',
  'verified',
  'closed',
] as const

/** Mirrors the server's flow: one step forward, or back to planning when verification fails. */
export const NEXT: Record<string, string[]> = {
  open: ['under_investigation'],
  under_investigation: ['corrective_action_planned'],
  corrective_action_planned: ['corrective_action_taken'],
  corrective_action_taken: ['verified'],
  verified: ['closed', 'corrective_action_planned'],
  closed: [],
}

export const SEVERITIES = ['minor', 'major', 'critical'] as const
export const SOURCES = [
  'inspection',
  'audit',
  'client',
  'supplier',
  'other',
] as const
export const ROOT_CAUSES = [
  'material',
  'workmanship',
  'design',
  'process',
  'supplier',
  'other',
] as const
export const DISPOSITIONS = [
  'rework',
  'repair',
  'use_as_is',
  'scrap',
  'return_to_supplier',
] as const
export const ACTION_STATUSES = [
  'open',
  'in_progress',
  'done',
  'verified',
  'cancelled',
] as const

export type Filters = { status: string; severity: string; search: string }

const keys = {
  all: ['ncr'] as const,
  list: (projectId: number, f: Filters) =>
    ['ncr', projectId, 'list', f] as const,
  one: (id: number) => ['ncr', 'one', id] as const,
  history: (id: number) => ['ncr', 'history', id] as const,
}

export function useNcrs(projectId: number, f: Filters) {
  return useQuery({
    queryKey: keys.list(projectId, f),
    queryFn: async () =>
      (
        await unwrap(
          api.GET('/api/v1/ncr/', {
            params: {
              query: {
                project_id: projectId,
                items_per_page: 100,
                status: (f.status || undefined) as never,
                severity: (f.severity || undefined) as never,
                search: f.search || undefined,
              },
            },
          })
        )
      ).data,
  })
}

export function useNcr(id: number | null) {
  return useQuery({
    queryKey: keys.one(id ?? 0),
    enabled: Boolean(id),
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/ncr/{ncr_id}', {
          params: { path: { ncr_id: id ?? 0 } },
        })
      ),
  })
}

export function useNcrHistory(id: number) {
  return useQuery({
    queryKey: keys.history(id),
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/ncr/{ncr_id}/history', {
          params: { path: { ncr_id: id } },
        })
      ) as Promise<
        {
          from_status: string | null
          to_status: string
          changed_by_name: string | null
          note: string | null
          changed_at: string | null
        }[]
      >,
  })
}

export function useCreateNcr() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: NcrCreate) => unwrap(api.POST('/api/v1/ncr/', { body })),
    onSuccess: () => void qc.invalidateQueries({ queryKey: keys.all }),
    onError: handleServerError,
  })
}

function useNcrWrite<T>(id: number, call: (v: T) => Promise<Ncr>) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: call,
    onSuccess: (data) => {
      qc.setQueryData(keys.one(id), data)
      void qc.invalidateQueries({
        queryKey: keys.all,
        predicate: (q) => q.queryKey[1] !== 'one',
      })
    },
    onError: handleServerError,
  })
}

const at = (id: number) => ({ params: { path: { ncr_id: id } } })

export function useUpdateNcr(id: number) {
  return useNcrWrite(id, (body: NcrUpdate) =>
    unwrap(api.PATCH('/api/v1/ncr/{ncr_id}', { ...at(id), body }))
  )
}

export function useNcrStatus(id: number) {
  return useNcrWrite(id, (body: { status: string; note?: string }) =>
    unwrap(
      api.PATCH('/api/v1/ncr/{ncr_id}/status', {
        ...at(id),
        body: body as never,
      })
    )
  )
}

export function useAddAction(id: number) {
  return useNcrWrite(id, (body: NcrActionCreate) =>
    unwrap(api.POST('/api/v1/ncr/{ncr_id}/actions', { ...at(id), body }))
  )
}

export function useUpdateAction(id: number) {
  return useNcrWrite(
    id,
    ({ actionId, body }: { actionId: number; body: NcrActionUpdate }) =>
      unwrap(
        api.PATCH('/api/v1/ncr/{ncr_id}/actions/{action_id}', {
          params: { path: { ncr_id: id, action_id: actionId } },
          body,
        })
      )
  )
}

export function useDeleteAction(id: number) {
  return useNcrWrite(id, (actionId: number) =>
    unwrap(
      api.DELETE('/api/v1/ncr/{ncr_id}/actions/{action_id}', {
        params: { path: { ncr_id: id, action_id: actionId } },
      })
    )
  )
}

export function useContactOptions(enabled: boolean) {
  return useQuery({
    queryKey: ['contacts', 'options'],
    enabled,
    queryFn: async () =>
      (
        await unwrap(
          api.GET('/api/v1/contacts/', {
            params: { query: { items_per_page: 100 } },
          })
        )
      ).data,
  })
}
