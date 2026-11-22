import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, unwrap } from '@/api/client'
import type { components } from '@/api/schema'
import { handleServerError } from '@/lib/handle-server-error'

export type Submittal = components['schemas']['SubmittalRead']
export type SubmittalDetail = components['schemas']['SubmittalDetail']
export type Review = components['schemas']['SubmittalReviewRead']
export type Revision = components['schemas']['SubmittalRevisionRead']
export type WorkflowStep = components['schemas']['SubmittalWorkflowStep']
export type Reviewer = components['schemas']['SubmittalReviewerOption']
export type HistoryEntry = components['schemas']['SubmittalHistoryRead']
export type Decision =
  components['schemas']['SubmittalReviewDecision']['decision']

export const TYPES = [
  'shop_drawing',
  'product_data',
  'sample',
  'method_statement',
  'test_report',
  'om_manual',
] as const

export const STATUSES = [
  'draft',
  'submitted',
  'under_review',
  'approved',
  'approved_as_noted',
  'revise_and_resubmit',
  'rejected',
  'closed',
] as const

export const DECISIONS: Decision[] = [
  'approved',
  'approved_as_noted',
  'revise_and_resubmit',
  'rejected',
]

export const typeLabel = (type: string) =>
  type === 'om_manual'
    ? 'O&M manual'
    : type.replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase())

export type RegisterFilters = {
  status?: string
  reviewer?: string
  spec_section?: string
  overdue?: boolean
  search?: string
}

export const submittalKeys = {
  all: (projectId: number) => ['submittals', projectId] as const,
  list: (projectId: number, filters: RegisterFilters) =>
    ['submittals', projectId, 'list', filters] as const,
  one: (id: number) => ['submittals', 'one', id] as const,
  revisions: (id: number) => ['submittals', 'one', id, 'revisions'] as const,
  history: (id: number) => ['submittals', 'one', id, 'history'] as const,
}

export function useRegister(projectId: number, filters: RegisterFilters) {
  return useQuery({
    queryKey: submittalKeys.list(projectId, filters),
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/submittals/', {
          params: {
            query: {
              project_id: projectId,
              items_per_page: 100,
              status: (filters.status || undefined) as never,
              reviewer: filters.reviewer || undefined,
              spec_section: filters.spec_section || undefined,
              overdue: filters.overdue || undefined,
              search: filters.search || undefined,
            },
          },
        })
      ),
  })
}

export function useSubmittal(id: number | null) {
  return useQuery({
    queryKey: submittalKeys.one(id ?? 0),
    enabled: id !== null,
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/submittals/{submittal_id}', {
          params: { path: { submittal_id: id ?? 0 } },
        })
      ),
  })
}

export function useRevisions(id: number) {
  return useQuery({
    queryKey: submittalKeys.revisions(id),
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/submittals/{submittal_id}/revisions', {
          params: { path: { submittal_id: id } },
        })
      ),
  })
}

export function useHistory(id: number) {
  return useQuery({
    queryKey: submittalKeys.history(id),
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/submittals/{submittal_id}/history', {
          params: { path: { submittal_id: id } },
        })
      ),
  })
}

export function useReviewers(enabled = true) {
  return useQuery({
    queryKey: ['submittals', 'reviewers'],
    enabled,
    queryFn: async () =>
      (
        await unwrap(
          api.GET('/api/v1/submittals/reviewers/', {
            params: { query: { items_per_page: 100 } },
          })
        )
      ).data,
  })
}

/** Refresh everything that shows submittals after a change. */
export function useRefresh(projectId: number) {
  const queryClient = useQueryClient()
  return () => {
    void queryClient.invalidateQueries({
      queryKey: submittalKeys.all(projectId),
    })
    void queryClient.invalidateQueries({ queryKey: ['submittals', 'one'] })
  }
}

/** A POST action on one submittal: submit, review, revise or close. */
export function useAction(
  projectId: number,
  action: 'submit' | 'review' | 'revise' | 'close'
) {
  const refresh = useRefresh(projectId)
  return useMutation({
    mutationFn: ({ id, body }: { id: number; body: object }) => {
      const params = { params: { path: { submittal_id: id } } }
      switch (action) {
        case 'submit':
          return unwrap(
            api.POST('/api/v1/submittals/{submittal_id}/submit', {
              ...params,
              body: body as never,
            })
          )
        case 'review':
          return unwrap(
            api.POST('/api/v1/submittals/{submittal_id}/review', {
              ...params,
              body: body as never,
            })
          )
        case 'revise':
          return unwrap(
            api.POST('/api/v1/submittals/{submittal_id}/revise', {
              ...params,
              body: body as never,
            })
          )
        case 'close':
          return unwrap(
            api.POST('/api/v1/submittals/{submittal_id}/close', {
              ...params,
              body: body as never,
            })
          )
      }
    },
    onSuccess: refresh,
    onError: handleServerError,
  })
}
/** Steps with at least one reviewer, ready to send. */
export function cleanWorkflow(steps: WorkflowStep[]): WorkflowStep[] {
  return steps
    .filter((s) => s.reviewer_ids.length > 0)
    .map((s) => ({
      name: (s.name ?? '').trim(),
      reviewer_ids: s.reviewer_ids,
      parallel: s.reviewer_ids.length > 1 && Boolean(s.parallel),
    }))
}
