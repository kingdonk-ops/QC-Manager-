import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, unwrap } from '@/api/client'
import type { components } from '@/api/schema'
import { handleServerError } from '@/lib/handle-server-error'

type S = components['schemas']
export type Heat = S['HeatRead']
export type HeatDetail = S['HeatDetail']
export type Receipt = S['MaterialReceiptRead']
export type Hold = S['MaterialHoldRead']
export type HeatTrace = S['HeatTrace']
export type Warning = S['MaterialReadinessWarning']

export const PRODUCT_FORMS = [
  'pipe',
  'fitting',
  'flange',
  'plate',
  'bolting',
  'gasket',
  'valve',
  'structural',
  'consumable',
  'coating',
  'insulation',
  'other',
] as const
export const HEAT_STATUSES = [
  'expected',
  'available',
  'quarantined',
  'rejected',
] as const

const ROOT = ['materials'] as const
const page = { items_per_page: 100 }

/** A mutation that refreshes every materials query and toasts the backend's refusal. */
export function useAct<V, R = unknown>(fn: (v: V) => Promise<R>) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ROOT }),
    onError: handleServerError,
  })
}

export function useHeats(
  projectId: number,
  filter: { status?: string; search?: string }
) {
  return useQuery({
    queryKey: [...ROOT, projectId, 'heats', filter],
    queryFn: async () =>
      (
        await unwrap(
          api.GET('/api/v1/materials/heats/', {
            params: {
              query: {
                project_id: projectId,
                ...page,
                status: (filter.status || undefined) as never,
                search: filter.search || undefined,
              },
            },
          })
        )
      ).data,
  })
}

export function useHeat(id: number | undefined) {
  return useQuery({
    queryKey: [...ROOT, 'heat', id],
    enabled: !!id,
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/materials/heats/{heat_id}', {
          params: { path: { heat_id: id! } },
        })
      ),
  })
}

export function useReceipts(projectId: number) {
  return useQuery({
    queryKey: [...ROOT, projectId, 'receipts'],
    queryFn: async () =>
      (
        await unwrap(
          api.GET('/api/v1/materials/receipts/', {
            params: { query: { project_id: projectId, ...page } },
          })
        )
      ).data,
  })
}

export function useHolds(projectId: number) {
  return useQuery({
    queryKey: [...ROOT, projectId, 'holds'],
    queryFn: async () =>
      (
        await unwrap(
          api.GET('/api/v1/materials/holds/', {
            params: {
              query: { project_id: projectId, ...page, status: 'open' },
            },
          })
        )
      ).data,
  })
}

export function useWarnings(projectId: number) {
  return useQuery({
    queryKey: [...ROOT, projectId, 'warnings'],
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/materials/warnings', {
          params: { query: { project_id: projectId } },
        })
      ),
  })
}

export function useNodeTrace(nodeId: number | undefined) {
  return useQuery({
    queryKey: [...ROOT, 'trace', nodeId],
    enabled: !!nodeId,
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/materials/trace/nodes/{node_id}', {
          params: { path: { node_id: nodeId! } },
        })
      ),
  })
}

export function useNodeSearch(projectId: number, search: string) {
  return useQuery({
    queryKey: ['asset-tree', projectId, 'node-search', search],
    enabled: search.length > 0,
    queryFn: async () =>
      (
        await unwrap(
          api.GET('/api/v1/asset-tree/nodes/', {
            params: {
              query: { project_id: projectId, search, items_per_page: 20 },
            },
          })
        )
      ).data,
  })
}

export const materialsApi = {
  createReceipt: (body: S['MaterialReceiptIn']) =>
    unwrap(api.POST('/api/v1/materials/receipts/', { body })),
  createHeat: (body: S['HeatIn']) =>
    unwrap(api.POST('/api/v1/materials/heats/', { body })),
  receive: (id: number, received_on: string) =>
    unwrap(
      api.POST('/api/v1/materials/heats/{heat_id}/receive', {
        params: { path: { heat_id: id } },
        body: { received_on },
      })
    ),
  addCertificate: (id: number, body: S['MillCertificateIn']) =>
    unwrap(
      api.POST('/api/v1/materials/heats/{heat_id}/certificates', {
        params: { path: { heat_id: id } },
        body,
      })
    ),
  verify: (id: number, status: 'verified' | 'rejected', reason?: string) =>
    unwrap(
      api.POST('/api/v1/materials/certificates/{certificate_id}/verify', {
        params: { path: { certificate_id: id } },
        body: { status, reason: reason || null },
      })
    ),
  hold: (id: number, reason: string) =>
    unwrap(
      api.POST('/api/v1/materials/heats/{heat_id}/holds', {
        params: { path: { heat_id: id } },
        body: { reason },
      })
    ),
  closeHold: (id: number, status: 'released' | 'rejected') =>
    unwrap(
      api.POST('/api/v1/materials/holds/{hold_id}/close', {
        params: { path: { hold_id: id } },
        body: { status },
      })
    ),
  issue: (body: S['MaterialIssueIn']) =>
    unwrap(api.POST('/api/v1/materials/issues/', { body })),
}
