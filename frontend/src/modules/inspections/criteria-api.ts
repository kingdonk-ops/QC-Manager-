import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ApiError, api, unwrap } from '@/api/client'
import type { components } from '@/api/schema'
import { handleServerError } from '@/lib/handle-server-error'

type S = components['schemas']
export type Criterion = S['CriterionRead']
export type CriterionBody = S['CriterionCreate']
export type CriterionPatch = S['CriterionUpdate']
/** What the form edits: the body without the project and the supplementary data. */
export type CriterionFields = Omit<CriterionBody, 'project_id' | 'supplementary'>
export type InspectionSettings = S['InspectionSettingsRead']

/** The server's own wording for a refusal (a conflict, a duplicate code), for showing verbatim. */
export function errorText(error: unknown): string {
  if (error instanceof ApiError && typeof error.detail === 'string')
    return error.detail
  return error instanceof Error ? error.message : 'Something went wrong!'
}

export const criteriaKeys = {
  list: (projectId: number, category: string, active: string) =>
    ['inspections', projectId, 'criteria', category, active] as const,
  settings: (projectId: number) =>
    ['inspections', projectId, 'settings'] as const,
}

/** The project's criteria library ordered by code; `active` is '', 'true' or 'false'. */
export function useCriteria(
  projectId: number,
  filters: { category?: string; active?: string } = {}
) {
  const category = filters.category ?? ''
  const active = filters.active ?? ''
  return useQuery({
    queryKey: criteriaKeys.list(projectId, category, active),
    queryFn: async () =>
      (
        await unwrap(
          api.GET('/api/v1/inspections/criteria/', {
            params: {
              query: {
                project_id: projectId,
                items_per_page: 100,
                category: category || undefined,
                active: active === '' ? undefined : active === 'true',
              },
            },
          })
        )
      ).data as Criterion[],
  })
}

/** Create (no id) or edit a criterion. Errors are left to the caller so the form can show them verbatim. */
export function useSaveCriterion(projectId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, body }: { id?: number; body: CriterionFields }) =>
      id
        ? unwrap(
            api.PATCH('/api/v1/inspections/criteria/{criterion_id}', {
              params: { path: { criterion_id: id } },
              body: body as CriterionPatch,
            })
          )
        : unwrap(
            api.POST('/api/v1/inspections/criteria/', {
              body: { ...body, project_id: projectId, supplementary: {} },
            })
          ),
    onSuccess: () =>
      void qc.invalidateQueries({ queryKey: ['inspections', projectId] }),
  })
}

export function useDeleteCriterion(projectId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) =>
      unwrap(
        api.DELETE('/api/v1/inspections/criteria/{criterion_id}', {
          params: { path: { criterion_id: id } },
        })
      ),
    onSuccess: () =>
      void qc.invalidateQueries({ queryKey: ['inspections', projectId] }),
  })
}

export function useInspectionSettings(projectId: number) {
  return useQuery({
    queryKey: criteriaKeys.settings(projectId),
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/inspections/settings', {
          params: { query: { project_id: projectId } },
        })
      ),
  })
}

export function useUpdateInspectionSettings(projectId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: S['InspectionSettingsUpdate']) =>
      unwrap(
        api.PATCH('/api/v1/inspections/settings', {
          params: { query: { project_id: projectId } },
          body,
        })
      ),
    onSuccess: () =>
      void qc.invalidateQueries({ queryKey: criteriaKeys.settings(projectId) }),
    onError: handleServerError,
  })
}
