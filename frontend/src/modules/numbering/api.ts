import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, unwrap } from '@/api/client'
import type { components } from '@/api/schema'
import { handleServerError } from '@/lib/handle-server-error'

type S = components['schemas']
export type Scheme = S['SchemeRead']
export type SchemeIn = S['SchemeIn']
export type SchemeUpdate = S['SchemeUpdate']
export type PreviewIn = S['PreviewIn']
export type Allocation = S['AllocationRead']

const keys = {
  all: ['numbering'] as const,
  schemes: (projectId: number) => ['numbering', projectId, 'schemes'] as const,
  allocations: (projectId: number, kind: string) =>
    ['numbering', projectId, 'allocations', kind] as const,
}

export function useSchemes(projectId: number) {
  return useQuery({
    queryKey: keys.schemes(projectId),
    queryFn: async () =>
      (
        await unwrap(
          api.GET('/api/v1/numbering/schemes/', {
            params: { query: { project_id: projectId, items_per_page: 100 } },
          })
        )
      ).data,
  })
}

export function useAllocations(projectId: number, kind: string) {
  return useQuery({
    queryKey: keys.allocations(projectId, kind),
    queryFn: async () =>
      (
        await unwrap(
          api.GET('/api/v1/numbering/allocations/', {
            params: {
              query: {
                project_id: projectId,
                record_kind: kind || undefined,
                items_per_page: 100,
              },
            },
          })
        )
      ).data,
  })
}

function useInvalidating<T, R>(call: (v: T) => Promise<R>) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: call,
    onSuccess: () => void qc.invalidateQueries({ queryKey: keys.all }),
    onError: handleServerError,
  })
}

export function useSaveScheme(id: number | null) {
  return useInvalidating((body: SchemeIn) =>
    id
      ? unwrap(
          api.PATCH('/api/v1/numbering/schemes/{scheme_id}', {
            params: { path: { scheme_id: id } },
            body: {
              name: body.name,
              pattern: body.pattern,
              counter_scope: body.counter_scope,
              code_lists: body.code_lists,
              start_value: body.start_value,
              active: body.active,
            },
          })
        )
      : unwrap(api.POST('/api/v1/numbering/schemes/', { body }))
  )
}

export function useAllocate(schemeId: number) {
  return useInvalidating((values: Record<string, string>) =>
    unwrap(
      api.POST('/api/v1/numbering/schemes/{scheme_id}/allocate', {
        params: { path: { scheme_id: schemeId } },
        body: { values },
      })
    )
  )
}

export function useVoid() {
  return useInvalidating(({ id, reason }: { id: number; reason: string }) =>
    unwrap(
      api.POST('/api/v1/numbering/allocations/{allocation_id}/void', {
        params: { path: { allocation_id: id } },
        body: { reason },
      })
    )
  )
}

function useDebounced<T>(value: T, ms: number): T {
  const [current, setCurrent] = useState(value)
  useEffect(() => {
    const timer = setTimeout(() => setCurrent(value), ms)
    return () => clearTimeout(timer)
  }, [value, ms])
  return current
}

/** The server's preview of a pattern, refreshed 300 ms after the last edit. */
export function usePreview(body: PreviewIn) {
  const debounced = useDebounced(JSON.stringify(body), 300)
  return useQuery({
    queryKey: ['numbering', 'preview', debounced],
    enabled: body.pattern.trim().length > 0,
    placeholderData: (previous) => previous,
    queryFn: () =>
      unwrap(
        api.POST('/api/v1/numbering/preview', {
          body: JSON.parse(debounced) as PreviewIn,
        })
      ),
  })
}
