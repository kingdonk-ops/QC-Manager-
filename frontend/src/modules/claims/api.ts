import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, unwrap } from '@/api/client'
import type { components } from '@/api/schema'
import { handleServerError } from '@/lib/handle-server-error'

export type Claim = components['schemas']['ClaimRead']
export type ClaimDetail = components['schemas']['ClaimDetail']
export type ClaimLine = components['schemas']['LineRead']
export type RateItem = components['schemas']['RateItemRead']

/** Next statuses, with the permission each needs. */
export const MOVES: Record<string, { to: string; permission: string }[]> = {
  draft: [{ to: 'submitted', permission: 'claims.submit' }],
  submitted: [
    { to: 'certified', permission: 'claims.approve' },
    { to: 'draft', permission: 'claims.submit' },
  ],
  certified: [{ to: 'paid', permission: 'claims.approve' }],
  paid: [],
}

/** The most a line may claim to date: verified quantity for work, the approved share (1) for a variation. */
export function claimLimit(line: {
  kind: string
  verified_qty: string | number
  contract_qty: string | number
}) {
  return Number(line.kind === 'work' ? line.verified_qty : line.contract_qty)
}

const keys = {
  all: (p: number) => ['claims', p] as const,
  list: (p: number) => ['claims', p, 'list'] as const,
  one: (p: number, id: number) => ['claims', p, 'one', id] as const,
  rates: (p: number) => ['claims', p, 'rates'] as const,
}

function useRefresh(projectId: number) {
  const qc = useQueryClient()
  return () => void qc.invalidateQueries({ queryKey: keys.all(projectId) })
}

export function useClaims(projectId: number) {
  return useQuery({
    queryKey: keys.list(projectId),
    queryFn: async () =>
      (
        await unwrap(
          api.GET('/api/v1/claims/', {
            params: { query: { project_id: projectId, items_per_page: 200 } },
          })
        )
      ).data,
  })
}

export function useClaim(projectId: number, id: number | undefined) {
  return useQuery({
    queryKey: keys.one(projectId, id ?? 0),
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/claims/{claim_id}', {
          params: { path: { claim_id: id! } },
        })
      ),
    enabled: !!id,
  })
}

export function useRateItems(projectId: number) {
  return useQuery({
    queryKey: keys.rates(projectId),
    queryFn: async () =>
      (
        await unwrap(
          api.GET('/api/v1/claims/rate-items/', {
            params: { query: { project_id: projectId, items_per_page: 1000 } },
          })
        )
      ).data,
  })
}

export function useRateActions(projectId: number) {
  const refresh = useRefresh(projectId)
  const seed = useMutation({
    mutationFn: () =>
      unwrap(
        api.POST('/api/v1/claims/rate-items/from-tree', {
          params: { query: { project_id: projectId } },
        })
      ),
    onSuccess: refresh,
    onError: handleServerError,
  })
  const create = useMutation({
    mutationFn: (body: { code: string; description: string }) =>
      unwrap(
        api.POST('/api/v1/claims/rate-items/', {
          body: { ...body, project_id: projectId } as never,
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
      value: string | null
    }) =>
      unwrap(
        api.PATCH('/api/v1/claims/rate-items/{item_id}', {
          params: { path: { item_id: id } },
          body: { [field]: value } as never,
        })
      ),
    onSuccess: refresh,
    onError: (e) => {
      handleServerError(e)
      refresh()
    },
  })
  const remove = useMutation({
    mutationFn: (id: number) =>
      unwrap(
        api.DELETE('/api/v1/claims/rate-items/{item_id}', {
          params: { path: { item_id: id } },
        })
      ),
    onSuccess: refresh,
    onError: handleServerError,
  })
  return { seed, create, update, remove }
}

export function useClaimActions(projectId: number) {
  const refresh = useRefresh(projectId)
  const create = useMutation({
    mutationFn: (body: {
      period_start: string
      period_end: string
      retention_pct: string
      retention_cap: string | null
    }) =>
      unwrap(
        api.POST('/api/v1/claims/', {
          body: { ...body, project_id: projectId },
        })
      ),
    onSuccess: refresh,
    onError: handleServerError,
  })
  const reload = useMutation({
    mutationFn: (id: number) =>
      unwrap(
        api.POST('/api/v1/claims/{claim_id}/refresh', {
          params: { path: { claim_id: id } },
        })
      ),
    onSuccess: refresh,
    onError: handleServerError,
  })
  const line = useMutation({
    mutationFn: ({
      claimId,
      lineId,
      qty,
    }: {
      claimId: number
      lineId: number
      qty: string
    }) =>
      unwrap(
        api.PATCH('/api/v1/claims/{claim_id}/lines/{line_id}', {
          params: { path: { claim_id: claimId, line_id: lineId } },
          body: { to_date_qty: qty },
        })
      ),
    onSuccess: refresh,
    onError: (e) => {
      handleServerError(e)
      refresh()
    },
  })
  const move = useMutation({
    mutationFn: ({
      id,
      status,
      amount,
      on,
      reference,
    }: {
      id: number
      status: string
      amount?: string
      on?: string
      reference?: string
    }) =>
      unwrap(
        api.PATCH('/api/v1/claims/{claim_id}/status', {
          params: { path: { claim_id: id } },
          body: {
            status: status as never,
            certified_amount: status === 'certified' ? amount || null : null,
            paid_amount: status === 'paid' ? amount || null : null,
            on: on || null,
            client_reference: reference || null,
          },
        })
      ),
    onSuccess: refresh,
    onError: handleServerError,
  })
  const remove = useMutation({
    mutationFn: (id: number) =>
      unwrap(
        api.DELETE('/api/v1/claims/{claim_id}', {
          params: { path: { claim_id: id } },
        })
      ),
    onSuccess: refresh,
    onError: handleServerError,
  })
  return { create, reload, line, move, remove }
}

export const pdfUrl = (id: number) => `/api/v1/claims/${id}/pdf`
export const exportUrl = (projectId: number) =>
  `/api/v1/claims/export?project_id=${projectId}&format=xlsx`
