import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, unwrap } from '@/api/client'
import type { components } from '@/api/schema'
import { handleServerError } from '@/lib/handle-server-error'

type S = components['schemas']
export type Template = S['ChecklistTemplateRead']
export type TemplateSection = S['ChecklistSection']
export type TemplateItem = S['ChecklistItem']
export type TemplateBody = S['ChecklistTemplateIn']
export type Inspection = S['InspectionRead']
export type InspectionItem = S['InspectionItemRead']
export type ItemAnswer = S['InspectionItemAnswer']
export type FollowUp = S['InspectionFollowUp']
export type Completion = S['InspectionCompletion']
export type Trends = S['InspectionTrends']

export const STATUSES = [
  'planned',
  'requested',
  'in_progress',
  'submitted',
  'returned',
  'completed',
  'closed',
] as const

export const keys = {
  all: ['inspections'] as const,
  templates: (projectId: number) =>
    ['inspections', projectId, 'templates'] as const,
  list: (projectId: number, status: string) =>
    ['inspections', projectId, 'list', status] as const,
  one: (id: number) => ['inspections', 'one', id] as const,
  trends: (projectId: number, groupBy: string) =>
    ['inspections', projectId, 'trends', groupBy] as const,
  history: (id: number) => ['inspections', 'history', id] as const,
}

export function useTemplates(projectId: number) {
  return useQuery({
    queryKey: keys.templates(projectId),
    queryFn: async () =>
      (
        await unwrap(
          api.GET('/api/v1/inspections/templates/', {
            params: { query: { project_id: projectId, items_per_page: 100 } },
          })
        )
      ).data,
  })
}

export function useSaveTemplate(projectId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, body }: { id?: number; body: TemplateBody }) => {
      if (id) {
        const { project_id: _, kind: __, ...rest } = body
        return unwrap(
          api.PATCH('/api/v1/inspections/templates/{template_id}', {
            params: { path: { template_id: id } },
            body: rest,
          })
        )
      }
      return unwrap(api.POST('/api/v1/inspections/templates/', { body }))
    },
    onSuccess: () =>
      void qc.invalidateQueries({ queryKey: keys.templates(projectId) }),
    onError: handleServerError,
  })
}

export function useTemplateAction(projectId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({
      id,
      action,
    }: {
      id?: number
      action: 'duplicate' | 'delete' | 'starter'
    }) => {
      if (action === 'starter')
        return unwrap(
          api.POST('/api/v1/inspections/templates/starter', {
            body: { project_id: projectId },
          })
        )
      const path = { params: { path: { template_id: id ?? 0 } } }
      if (action === 'duplicate')
        return unwrap(
          api.POST(
            '/api/v1/inspections/templates/{template_id}/duplicate',
            path
          )
        )
      return unwrap(
        api.DELETE('/api/v1/inspections/templates/{template_id}', path)
      )
    },
    onSuccess: () =>
      void qc.invalidateQueries({ queryKey: keys.templates(projectId) }),
    onError: handleServerError,
  })
}

export function useInspections(projectId: number, status: string) {
  return useQuery({
    queryKey: keys.list(projectId, status),
    queryFn: async () =>
      (
        await unwrap(
          api.GET('/api/v1/inspections/', {
            params: {
              query: {
                project_id: projectId,
                items_per_page: 100,
                status: (status || undefined) as never,
              },
            },
          })
        )
      ).data,
  })
}

export function useInspection(id: number) {
  return useQuery({
    queryKey: keys.one(id),
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/inspections/{inspection_id}', {
          params: { path: { inspection_id: id } },
        })
      ),
  })
}

export function useTrends(projectId: number, groupBy: 'trade' | 'location') {
  return useQuery({
    queryKey: keys.trends(projectId, groupBy),
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/inspections/trends', {
          params: { query: { project_id: projectId, group_by: groupBy } },
        })
      ),
  })
}

export function useCreateInspection() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: S['InspectionCreate']) =>
      unwrap(api.POST('/api/v1/inspections/', { body })),
    onSuccess: () => void qc.invalidateQueries({ queryKey: keys.all }),
    onError: handleServerError,
  })
}

/** Every write on one inspection answers with the whole inspection; keep the cache in step. */
function useInspectionWrite<T>(
  id: number,
  call: (body: T) => Promise<Inspection>
) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: call,
    onSuccess: (data) => {
      qc.setQueryData(keys.one(id), data)
      void qc.invalidateQueries({
        queryKey: keys.all,
        predicate: (q) => q.queryKey[1] !== 'one',
      })
      void qc.invalidateQueries({ queryKey: ['tasks'] })
      void qc.invalidateQueries({ queryKey: ['ncr'] })
    },
    onError: handleServerError,
  })
}

export function useFillItems(id: number) {
  return useInspectionWrite(id, (items: ItemAnswer[]) =>
    unwrap(
      api.PATCH('/api/v1/inspections/{inspection_id}/items', {
        params: { path: { inspection_id: id } },
        body: { items },
      })
    )
  )
}

export function useUpdateInspection(id: number) {
  return useInspectionWrite(id, (body: S['InspectionUpdate']) =>
    unwrap(
      api.PATCH('/api/v1/inspections/{inspection_id}', {
        params: { path: { inspection_id: id } },
        body,
      })
    )
  )
}

export function useComplete(id: number) {
  return useInspectionWrite(id, (body: Completion) =>
    unwrap(
      api.POST('/api/v1/inspections/{inspection_id}/complete', {
        params: { path: { inspection_id: id } },
        body,
      })
    )
  )
}

export function useSetStatus(id: number) {
  return useInspectionWrite(id, (status: string) =>
    unwrap(
      api.PATCH('/api/v1/inspections/{inspection_id}/status', {
        params: { path: { inspection_id: id } },
        body: { status: status as never },
      })
    )
  )
}

/** Outcome a numeric reading scores, mirroring the server's rule, for instant feedback. */
export function readingOutcome(item: InspectionItem, reading: number | null) {
  if (reading === null || Number.isNaN(reading)) return null
  if (item.min_value !== null && reading < item.min_value) return 'fail'
  if (item.max_value !== null && reading > item.max_value) return 'fail'
  return 'pass'
}

export function limitHint(item: {
  min_value?: number | null
  max_value?: number | null
  unit?: string | null
}) {
  const unit = item.unit ? ` ${item.unit}` : ''
  const lo = item.min_value ?? null
  const hi = item.max_value ?? null
  if (lo !== null && hi !== null) return `${lo}–${hi}${unit}`
  if (lo !== null) return `≥ ${lo}${unit}`
  if (hi !== null) return `≤ ${hi}${unit}`
  return unit.trim()
}
