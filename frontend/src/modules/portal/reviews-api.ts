import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, unwrap } from '@/api/client'
import type { components } from '@/api/schema'
import { handleServerError } from '@/lib/handle-server-error'

type S = components['schemas']
export type Review = S['PlanReviewRead']
export type ReviewDetail = S['PlanReviewDetail']

export const KINDS = [
  'work_plan',
  'itp',
  'method_statement',
  'schedule',
  'drawing',
  'other',
] as const

const keys = {
  all: ['plan-reviews'] as const,
  list: (projectId: number, status: string) =>
    ['plan-reviews', projectId, status] as const,
  one: (id: number) => ['plan-reviews', 'one', id] as const,
}

export function useReviews(projectId: number, status: string) {
  return useQuery({
    queryKey: keys.list(projectId, status),
    enabled: projectId > 0,
    queryFn: async () =>
      (
        await unwrap(
          api.GET('/api/v1/portal/reviews/', {
            params: {
              query: {
                project_id: projectId,
                status: (status || undefined) as never,
              },
            },
          })
        )
      ).data,
  })
}

export function useReview(id: number | null) {
  return useQuery({
    queryKey: keys.one(id ?? 0),
    enabled: Boolean(id),
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/portal/reviews/{review_id}', {
          params: { path: { review_id: id ?? 0 } },
        })
      ),
  })
}

function useWrite<T>(call: (v: T) => Promise<ReviewDetail>) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: call,
    onSuccess: (data) => {
      qc.setQueryData(keys.one(data.id), data)
      void qc.invalidateQueries({
        queryKey: keys.all,
        predicate: (q) => q.queryKey[1] !== 'one',
      })
    },
    onError: handleServerError,
  })
}

const at = (id: number) => ({ params: { path: { review_id: id } } })

export function useCreateReview() {
  return useWrite((body: S['PlanReviewCreate']) =>
    unwrap(api.POST('/api/v1/portal/reviews/', { body }))
  )
}

export function useShare(id: number) {
  return useWrite((note: string) =>
    unwrap(
      api.POST('/api/v1/portal/reviews/{review_id}/share', {
        ...at(id),
        body: { note: note || null },
      })
    )
  )
}

export function useWithdraw(id: number) {
  return useWrite(() =>
    unwrap(api.POST('/api/v1/portal/reviews/{review_id}/withdraw', at(id)))
  )
}

export function useAddDocument(id: number) {
  return useWrite((fileId: number) =>
    unwrap(
      api.POST('/api/v1/portal/reviews/{review_id}/documents', {
        ...at(id),
        body: { file_id: fileId },
      })
    )
  )
}

export function useDecide(id: number) {
  return useWrite(
    ({
      documentId,
      decision,
      comment,
    }: {
      documentId: number
      decision: 'approved' | 'approved_with_comments' | 'rejected'
      comment: string
    }) =>
      unwrap(
        api.POST(
          '/api/v1/portal/reviews/{review_id}/documents/{document_id}/decision',
          {
            params: { path: { review_id: id, document_id: documentId } },
            body: { decision, comment: comment || null },
          }
        )
      )
  )
}

export function useComment(id: number) {
  return useWrite(
    ({ body, documentId }: { body: string; documentId: number | null }) =>
      unwrap(
        api.POST('/api/v1/portal/reviews/{review_id}/comments', {
          ...at(id),
          body: { body, document_id: documentId },
        })
      )
  )
}

export const downloadUrl = (reviewId: number, documentId: number) =>
  `/api/v1/portal/reviews/${reviewId}/documents/${documentId}/download`
