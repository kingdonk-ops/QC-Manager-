import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, unwrap } from '@/api/client'
import type { components } from '@/api/schema'
import { handleServerError } from '@/lib/handle-server-error'

type S = components['schemas']
export type Gate = S['QualityGateRead']
export type GateBody = S['GateCreate']
export type GateProceed = S['GateProceed']

export type GateFilters = {
  status?: string
  kind?: string
  attachment_kind?: string
  attachment_id?: number
  /** Every gate attached to or linked to this inspection record. */
  inspection_id?: number
}

export const gateKeys = {
  list: (projectId: number, f: GateFilters) =>
    [
      'inspections',
      projectId,
      'gates',
      f.status ?? '',
      f.kind ?? '',
      f.attachment_kind ?? '',
      f.attachment_id ?? 0,
      f.inspection_id ?? 0,
    ] as const,
  proceed: (projectId: number, kind: string, id: number) =>
    ['inspections', projectId, 'gates', 'can-proceed', kind, id] as const,
}

/** A project's gates, newest first, optionally narrowed by status, kind or attachment target. */
export function useGates(projectId: number, filters: GateFilters = {}) {
  return useQuery({
    queryKey: gateKeys.list(projectId, filters),
    queryFn: async () =>
      (
        await unwrap(
          api.GET('/api/v1/inspections/gates/', {
            params: {
              query: {
                project_id: projectId,
                items_per_page: 100,
                status: (filters.status || undefined) as never,
                kind: (filters.kind || undefined) as never,
                attachment_kind: (filters.attachment_kind || undefined) as never,
                attachment_id: filters.attachment_id,
                inspection_id: filters.inspection_id,
              },
            },
          })
        )
      ).data as Gate[],
  })
}

/** Whether work may go ahead on one entity, with the server's own lists of blocking gates and earlier holds. */
export function useCanProceed(
  projectId: number,
  attachmentKind: string,
  attachmentId: number
) {
  return useQuery({
    queryKey: gateKeys.proceed(projectId, attachmentKind, attachmentId),
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/inspections/gates/can-proceed', {
          params: {
            query: {
              project_id: projectId,
              attachment_kind: attachmentKind as never,
              attachment_id: attachmentId,
            },
          },
        })
      ),
  })
}

function useGateWrite<T>(call: (arg: T) => Promise<unknown>) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: call,
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['inspections'] }),
    onError: handleServerError,
  })
}

export function useCreateGate() {
  return useGateWrite((body: GateBody) =>
    unwrap(api.POST('/api/v1/inspections/gates/', { body }))
  )
}

export type GateAction =
  | { id: number; action: 'release'; body: S['GateRelease'] }
  | { id: number; action: 'waive'; body: S['GateWaive'] }
  | { id: number; action: 'void' }
  | { id: number; action: 'delete' }

/** Release, waive, void or delete one pending gate; the whole inspections cache is refreshed after. */
export function useGateAction() {
  return useGateWrite((a: GateAction) => {
    const params = { params: { path: { gate_id: a.id } } }
    switch (a.action) {
      case 'release':
        return unwrap(
          api.POST('/api/v1/inspections/gates/{gate_id}/release', {
            ...params,
            body: a.body,
          })
        )
      case 'waive':
        return unwrap(
          api.POST('/api/v1/inspections/gates/{gate_id}/waive', {
            ...params,
            body: a.body,
          })
        )
      case 'void':
        return unwrap(
          api.POST('/api/v1/inspections/gates/{gate_id}/void', params)
        )
      default:
        return unwrap(
          api.DELETE('/api/v1/inspections/gates/{gate_id}', params)
        )
    }
  })
}
