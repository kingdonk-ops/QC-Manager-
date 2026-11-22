import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, unwrap } from '@/api/client'
import type { components } from '@/api/schema'
import { handleServerError } from '@/lib/handle-server-error'

export type PurchaseOrder = components['schemas']['PurchaseOrderRead']
export type PurchaseOrderDetail = components['schemas']['PurchaseOrderDetail']
export type PurchaseOrderUpdate = components['schemas']['PurchaseOrderUpdate']
export type PoLine = components['schemas']['PoLineRead']
export type Receipt = components['schemas']['ReceiptRead']
export type ReceiptResult = components['schemas']['ReceiptResult']
export type Summary = components['schemas']['ProcurementSummary']

export const STATUSES = [
  'open',
  'draft',
  'sent',
  'partially_received',
  'fully_received',
  'closed',
  'cancelled',
] as const

const keys = {
  all: (projectId: number) => ['procurement', projectId] as const,
  list: (projectId: number, status: string, overdue: boolean) =>
    ['procurement', projectId, 'list', status, overdue] as const,
  summary: (projectId: number) =>
    ['procurement', projectId, 'summary'] as const,
  one: (projectId: number, id: number) =>
    ['procurement', projectId, 'one', id] as const,
}

export function usePurchaseOrders(
  projectId: number,
  status: string,
  overdue: boolean
) {
  return useQuery({
    queryKey: keys.list(projectId, status, overdue),
    queryFn: async () =>
      (
        await unwrap(
          api.GET('/api/v1/procurement/purchase-orders/', {
            params: {
              query: {
                project_id: projectId,
                items_per_page: 100,
                status: status || undefined,
                overdue: overdue || undefined,
              },
            },
          })
        )
      ).data,
  })
}

export function useSummary(projectId: number) {
  return useQuery({
    queryKey: keys.summary(projectId),
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/procurement/summary', {
          params: { query: { project_id: projectId } },
        })
      ),
  })
}

export function usePurchaseOrder(projectId: number, id: number) {
  return useQuery({
    queryKey: keys.one(projectId, id),
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/procurement/purchase-orders/{po_id}', {
          params: { path: { po_id: id } },
        })
      ),
  })
}

function useRefresh(projectId: number) {
  const queryClient = useQueryClient()
  return () =>
    void queryClient.invalidateQueries({ queryKey: keys.all(projectId) })
}

export function useCreatePurchaseOrder(projectId: number) {
  const refresh = useRefresh(projectId)
  return useMutation({
    mutationFn: (body: { title?: string; supplier_company_id?: number }) =>
      unwrap(
        api.POST('/api/v1/procurement/purchase-orders/', {
          body: { ...body, project_id: projectId },
        })
      ),
    onSuccess: refresh,
    onError: handleServerError,
  })
}

export function useUpdatePurchaseOrder(projectId: number, id: number) {
  const refresh = useRefresh(projectId)
  return useMutation({
    mutationFn: (body: PurchaseOrderUpdate) =>
      unwrap(
        api.PATCH('/api/v1/procurement/purchase-orders/{po_id}', {
          params: { path: { po_id: id } },
          body,
        })
      ),
    onSuccess: refresh,
    onError: handleServerError,
  })
}

export function usePoActions(projectId: number, id: number) {
  const refresh = useRefresh(projectId)
  const path = { params: { path: { po_id: id } } }
  const send = useMutation({
    mutationFn: (body: { to: string[]; message: string | null }) =>
      unwrap(
        api.POST('/api/v1/procurement/purchase-orders/{po_id}/send', {
          ...path,
          body,
        })
      ),
    onSuccess: refresh,
    onError: handleServerError,
  })
  const receive = useMutation({
    mutationFn: (body: components['schemas']['ReceiptCreate']) =>
      unwrap(
        api.POST('/api/v1/procurement/purchase-orders/{po_id}/receipts', {
          ...path,
          body,
        })
      ),
    onSuccess: refresh,
    onError: handleServerError,
  })
  const status = useMutation({
    mutationFn: (status: 'closed' | 'cancelled') =>
      unwrap(
        api.PATCH('/api/v1/procurement/purchase-orders/{po_id}/status', {
          ...path,
          body: { status },
        })
      ),
    onSuccess: refresh,
    onError: handleServerError,
  })
  const remove = useMutation({
    mutationFn: () =>
      unwrap(api.DELETE('/api/v1/procurement/purchase-orders/{po_id}', path)),
    onSuccess: refresh,
    onError: handleServerError,
  })
  return { send, receive, status, remove }
}

export function useLineMutations(projectId: number, poId: number) {
  const refresh = useRefresh(projectId)
  const add = useMutation({
    mutationFn: (body: { description: string }) =>
      unwrap(
        api.POST('/api/v1/procurement/purchase-orders/{po_id}/lines', {
          params: { path: { po_id: poId } },
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
      value: string | null
    }) =>
      unwrap(
        api.PATCH(
          '/api/v1/procurement/purchase-orders/{po_id}/lines/{line_id}',
          {
            params: { path: { po_id: poId, line_id: id } },
            body: { [field]: value } as never,
          }
        )
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
        api.DELETE(
          '/api/v1/procurement/purchase-orders/{po_id}/lines/{line_id}',
          {
            params: { path: { po_id: poId, line_id: id } },
          }
        )
      ),
    onSuccess: refresh,
    onError: handleServerError,
  })
  return { add, update, remove }
}

/** Supplier companies from the Contacts directory. */
export function useCompanies(search: string) {
  return useQuery({
    queryKey: ['contacts', 'companies', search],
    queryFn: async () =>
      (
        await unwrap(
          api.GET('/api/v1/contacts/companies/', {
            params: {
              query: { items_per_page: 100, search: search || undefined },
            },
          })
        )
      ).data,
    retry: false,
  })
}

/** The contacts at one company. */
export function useCompanyContacts(companyId: number | null | undefined) {
  return useQuery({
    queryKey: ['contacts', 'by-company', companyId],
    queryFn: async () =>
      (
        await unwrap(
          api.GET('/api/v1/contacts/', {
            params: { query: { items_per_page: 100, company_id: companyId! } },
          })
        )
      ).data,
    enabled: !!companyId,
    retry: false,
  })
}

export const pdfUrl = (id: number) =>
  `/api/v1/procurement/purchase-orders/${id}/pdf`
export const exportUrl = (projectId: number) =>
  `/api/v1/procurement/purchase-orders/export?project_id=${projectId}&format=xlsx`
