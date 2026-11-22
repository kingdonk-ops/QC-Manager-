import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, csrfHeaders, unwrap } from '@/api/client'
import type { components } from '@/api/schema'
import { handleServerError } from '@/lib/handle-server-error'

export type CdeDocument = components['schemas']['CdeDocumentRead']
export type CdeDocumentDetail = components['schemas']['CdeDocumentDetail']
export type CdeRevision = components['schemas']['CdeRevisionRead']
export type CdeConvention = components['schemas']['CdeNamingConventionRead']
export type CdeConventionIn = components['schemas']['CdeNamingConventionIn']
export type CdeState = 'wip' | 'shared' | 'published' | 'archived'

export const STATES: { id: CdeState; label: string }[] = [
  { id: 'wip', label: 'Work in progress' },
  { id: 'shared', label: 'Shared' },
  { id: 'published', label: 'Published' },
  { id: 'archived', label: 'Archived' },
]

export const SUITABILITY: Record<string, Record<string, string>> = {
  wip: { S0: 'Initial status (work in progress)' },
  shared: {
    S1: 'Suitable for coordination',
    S2: 'Suitable for information',
    S3: 'Suitable for review and comment',
    S4: 'Suitable for stage approval',
  },
  published: {
    ...Object.fromEntries(
      Array.from({ length: 9 }, (_, i) => [
        `A${i + 1}`,
        `Authorised and accepted, stage ${i + 1}`,
      ])
    ),
    CR: 'As constructed record',
  },
}

/** Where each state may go next. */
export const NEXT: Record<CdeState, CdeState[]> = {
  wip: ['shared', 'archived'],
  shared: ['wip', 'published', 'archived'],
  published: ['archived'],
  archived: [],
}

export const cdeKeys = {
  all: (projectId: number) => ['cde', projectId] as const,
  one: (id: number) => ['cde', 'one', id] as const,
}

export function useConvention(projectId: number) {
  return useQuery({
    queryKey: [...cdeKeys.all(projectId), 'naming'],
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/cde/naming/{project_id}', {
          params: { path: { project_id: projectId } },
        })
      ),
  })
}

export function useCounts(projectId: number) {
  return useQuery({
    queryKey: [...cdeKeys.all(projectId), 'counts'],
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/cde/documents/counts', {
          params: { query: { project_id: projectId } },
        })
      ),
  })
}

export function useDocuments(
  projectId: number,
  query: { state?: CdeState; awaiting_me?: boolean; search?: string }
) {
  return useQuery({
    queryKey: [...cdeKeys.all(projectId), 'list', query],
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/cde/documents/', {
          params: {
            query: {
              project_id: projectId,
              items_per_page: 100,
              state: query.awaiting_me ? undefined : query.state,
              awaiting_me: query.awaiting_me || undefined,
              search: query.search || undefined,
            },
          },
        })
      ),
  })
}

export function useDocument(id: number | null) {
  return useQuery({
    queryKey: cdeKeys.one(id ?? 0),
    enabled: id !== null,
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/cde/documents/{document_id}', {
          params: { path: { document_id: id ?? 0 } },
        })
      ),
  })
}

export function useDocumentHistory(id: number) {
  return useQuery({
    queryKey: [...cdeKeys.one(id), 'history'],
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/cde/documents/{document_id}/history', {
          params: { path: { document_id: id } },
        })
      ),
  })
}

export function useRefresh(projectId: number) {
  const queryClient = useQueryClient()
  return () => {
    void queryClient.invalidateQueries({ queryKey: cdeKeys.all(projectId) })
    void queryClient.invalidateQueries({ queryKey: ['cde', 'one'] })
  }
}

export function useChangeStatus(projectId: number) {
  const refresh = useRefresh(projectId)
  return useMutation({
    mutationFn: ({
      id,
      body,
    }: {
      id: number
      body: {
        state?: CdeState
        suitability?: string
        decision?: 'approve' | 'reject'
        comment?: string | null
      }
    }) =>
      unwrap(
        api.PATCH('/api/v1/cde/documents/{document_id}/status', {
          params: { path: { document_id: id } },
          body,
        })
      ),
    onSuccess: refresh,
    onError: handleServerError,
  })
}

export function useSaveConvention(projectId: number) {
  const refresh = useRefresh(projectId)
  return useMutation({
    mutationFn: (body: CdeConventionIn) =>
      unwrap(
        api.PUT('/api/v1/cde/naming/{project_id}', {
          params: { path: { project_id: projectId } },
          body,
        })
      ),
    onSuccess: refresh,
    onError: handleServerError,
  })
}

/** Multipart POST to a CDE endpoint; throws with the backend's message. */
export async function postForm(
  url: string,
  form: FormData
): Promise<CdeDocumentDetail> {
  const response = await fetch(url, {
    method: 'POST',
    credentials: 'include',
    headers: csrfHeaders(),
    body: form,
  })
  const body = await response.json().catch(() => ({}))
  if (!response.ok)
    throw new Error(
      typeof body.detail === 'string' ? body.detail : 'Upload failed'
    )
  return body as CdeDocumentDetail
}

export const downloadUrl = (
  id: number,
  revisionId?: number,
  inline = false
) => {
  const query = new URLSearchParams()
  if (revisionId) query.set('revision_id', String(revisionId))
  if (inline) query.set('inline', 'true')
  const qs = query.toString()
  return `/api/v1/cde/documents/${id}/download${qs ? `?${qs}` : ''}`
}
