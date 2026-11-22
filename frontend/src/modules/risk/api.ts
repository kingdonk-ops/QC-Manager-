import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, unwrap } from '@/api/client'
import type { components } from '@/api/schema'
import { handleServerError } from '@/lib/handle-server-error'

export type Risk = components['schemas']['RiskRead']
export type RiskMatrix = components['schemas']['RiskMatrix']
export type RiskCreate = components['schemas']['RiskCreate']
export type RiskUpdate = components['schemas']['RiskUpdate']
export type StatusChange = components['schemas']['RiskHistoryEntry']

export const CATEGORIES = [
  'technical',
  'financial',
  'schedule',
  'regulatory',
  'environmental',
  'safety',
  'commercial',
] as const
export const IMPACTS = ['low', 'medium', 'high', 'critical'] as const
export const RESPONSES = ['avoid', 'mitigate', 'transfer', 'accept'] as const
export const PROBABILITIES = [
  '0.1',
  '0.2',
  '0.3',
  '0.4',
  '0.5',
  '0.6',
  '0.7',
  '0.8',
  '0.9',
] as const

/** Where each status may go next; mirrors the backend's flow. */
export const NEXT_STATUS: Record<string, string[]> = {
  identified: ['assessed', 'mitigating', 'closed', 'occurred'],
  assessed: ['identified', 'mitigating', 'closed', 'occurred'],
  mitigating: ['assessed', 'closed', 'occurred'],
  occurred: ['mitigating', 'closed'],
  closed: ['identified'],
}

export type RiskFilter = {
  band?: string
  impact?: string
  status?: string
  open_only?: boolean
  search?: string
}

const keys = {
  all: (projectId: number) => ['risk', projectId] as const,
  list: (projectId: number, filter: RiskFilter) =>
    ['risk', projectId, 'list', filter] as const,
  matrix: (projectId: number) => ['risk', projectId, 'matrix'] as const,
  history: (id: number) => ['risk', 'history', id] as const,
}

export function useRisks(projectId: number, filter: RiskFilter) {
  return useQuery({
    queryKey: keys.list(projectId, filter),
    queryFn: async () =>
      (
        await unwrap(
          api.GET('/api/v1/risks/', {
            params: {
              query: {
                project_id: projectId,
                items_per_page: 100,
                band: (filter.band || undefined) as never,
                impact: (filter.impact || undefined) as never,
                status: (filter.status || undefined) as never,
                open_only: filter.open_only,
                search: filter.search || undefined,
                sort: 'exposure',
              },
            },
          })
        )
      ).data,
  })
}

export function useMatrix(projectId: number) {
  return useQuery({
    queryKey: keys.matrix(projectId),
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/risks/matrix', {
          params: { query: { project_id: projectId } },
        })
      ),
  })
}

export function useRiskHistory(id: number | undefined) {
  return useQuery({
    queryKey: keys.history(id ?? 0),
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/risks/{risk_id}/history', {
          params: { path: { risk_id: id! } },
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

export function useSaveRisk(projectId: number) {
  const refresh = useRefresh(projectId)
  return useMutation({
    mutationFn: ({ id, body }: { id?: number; body: RiskUpdate }) =>
      id
        ? unwrap(
            api.PATCH('/api/v1/risks/{risk_id}', {
              params: { path: { risk_id: id } },
              body,
            })
          )
        : unwrap(
            api.POST('/api/v1/risks/', {
              body: { ...body, project_id: projectId } as RiskCreate,
            })
          ),
    onSuccess: refresh,
    onError: handleServerError,
  })
}

export function useRiskStatus(projectId: number) {
  const refresh = useRefresh(projectId)
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, status }: { id: number; status: string }) =>
      unwrap(
        api.PATCH('/api/v1/risks/{risk_id}/status', {
          params: { path: { risk_id: id } },
          body: { status: status as never },
        })
      ),
    onSuccess: (risk) => {
      refresh()
      void queryClient.invalidateQueries({ queryKey: keys.history(risk.id) })
    },
    onError: handleServerError,
  })
}

export function useDeleteRisk(projectId: number) {
  const refresh = useRefresh(projectId)
  return useMutation({
    mutationFn: (id: number) =>
      unwrap(
        api.DELETE('/api/v1/risks/{risk_id}', {
          params: { path: { risk_id: id } },
        })
      ),
    onSuccess: refresh,
    onError: handleServerError,
  })
}

export const exportUrl = (projectId: number) =>
  `/api/v1/risks/export?project_id=${projectId}&format=xlsx`
