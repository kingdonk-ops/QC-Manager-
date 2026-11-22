import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query'
import { api, csrfHeaders, unwrap } from '@/api/client'
import type { components } from '@/api/schema'
import { handleServerError } from '@/lib/handle-server-error'

export type BoqSummary = components['schemas']['BoqSummary']
export type BoqDetail = components['schemas']['BoqDetail']
export type Position = components['schemas']['BoqPositionRead']
export type Line = components['schemas']['BoqLineRead']
export type Resource = components['schemas']['BoqResourceRead']
export type Assembly = components['schemas']['BoqAssemblyRead']
export type ValidationReport = components['schemas']['BoqValidationReport']
export type ImportReport = components['schemas']['BoqImportReport']
export type ResourceType = 'material' | 'labour' | 'equipment' | 'subcontract'
export type Ruleset = 'boq_quality' | 'din276' | 'nrm' | 'masterformat'

export const keys = {
  list: (projectId: number) => ['boq', 'list', projectId] as const,
  bill: (id: number) => ['boq', 'bill', id] as const,
  resources: ['boq', 'resources'] as const,
  assemblies: ['boq', 'assemblies'] as const,
  validation: (id: number) => ['boq', 'validate', id] as const,
}

export function useBoqs(projectId: number) {
  return useQuery({
    queryKey: keys.list(projectId),
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/boq/', {
          params: { query: { project_id: projectId, items_per_page: 100 } },
        })
      ),
  })
}

export function useBoq(id: number) {
  return useQuery({
    queryKey: keys.bill(id),
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/boq/{boq_id}', { params: { path: { boq_id: id } } })
      ),
  })
}

export function useCreateBoq(projectId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: { name: string; description?: string }) =>
      unwrap(
        api.POST('/api/v1/boq/', { body: { project_id: projectId, ...body } })
      ),
    onSuccess: () =>
      void queryClient.invalidateQueries({ queryKey: keys.list(projectId) }),
    onError: handleServerError,
  })
}

export function useDeleteBoq(projectId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) =>
      unwrap(
        api.DELETE('/api/v1/boq/{boq_id}', { params: { path: { boq_id: id } } })
      ),
    onSuccess: () =>
      void queryClient.invalidateQueries({ queryKey: keys.list(projectId) }),
    onError: handleServerError,
  })
}

/**
 * Every change to a bill answers with the whole bill (recomputed rates, totals, ordinals and the
 * undo state), which replaces the cached copy. A failure reloads the server's copy.
 */
export function useBillMutation<V>(
  boqId: number,
  call: (vars: V) => Promise<BoqDetail>
) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: call,
    onSuccess: (bill) => {
      queryClient.setQueryData(keys.bill(boqId), bill)
      void queryClient.invalidateQueries({ queryKey: keys.validation(boqId) })
    },
    onError: (error) => {
      handleServerError(error)
      void queryClient.invalidateQueries({ queryKey: keys.bill(boqId) })
    },
  })
}

type PositionBody = components['schemas']['BoqPositionCreate']
type PositionPatch = components['schemas']['BoqPositionUpdate']

export function useBillActions(boqId: number) {
  const queryClient = useQueryClient()
  const path = { params: { path: { boq_id: boqId } } }
  const at = (id: number) => ({ params: { path: { position_id: id } } })
  return {
    refresh: () => void queryClient.invalidateQueries({ queryKey: ['boq'] }),
    insert: useBillMutation(boqId, (body: PositionBody) =>
      unwrap(api.POST('/api/v1/boq/{boq_id}/positions', { ...path, body }))
    ),
    paste: useBillMutation(
      boqId,
      (body: components['schemas']['BoqBulkRows']) =>
        unwrap(
          api.POST('/api/v1/boq/{boq_id}/positions/bulk', { ...path, body })
        )
    ),
    update: useBillMutation(
      boqId,
      ({ id, ...body }: PositionPatch & { id: number }) =>
        unwrap(
          api.PATCH('/api/v1/boq/positions/{position_id}', { ...at(id), body })
        )
    ),
    remove: useBillMutation(boqId, (id: number) =>
      unwrap(api.DELETE('/api/v1/boq/positions/{position_id}', at(id)))
    ),
    move: useBillMutation(
      boqId,
      ({
        id,
        parent_id,
        before_id,
      }: {
        id: number
        parent_id: number | null
        before_id: number | null
      }) =>
        unwrap(
          api.POST('/api/v1/boq/positions/{position_id}/move', {
            ...at(id),
            body: { parent_id, before_id },
          })
        )
    ),
    addLine: useBillMutation(
      boqId,
      ({ id, ...body }: components['schemas']['BoqLineIn'] & { id: number }) =>
        unwrap(
          api.POST('/api/v1/boq/positions/{position_id}/resources', {
            ...at(id),
            body,
          })
        )
    ),
    updateLine: useBillMutation(
      boqId,
      ({
        id,
        lineId,
        ...body
      }: components['schemas']['BoqLineUpdate'] & {
        id: number
        lineId: number
      }) =>
        unwrap(
          api.PATCH('/api/v1/boq/positions/{position_id}/resources/{line_id}', {
            params: { path: { position_id: id, line_id: lineId } },
            body,
          })
        )
    ),
    removeLine: useBillMutation(
      boqId,
      ({ id, lineId }: { id: number; lineId: number }) =>
        unwrap(
          api.DELETE(
            '/api/v1/boq/positions/{position_id}/resources/{line_id}',
            {
              params: { path: { position_id: id, line_id: lineId } },
            }
          )
        )
    ),
    applyAssembly: useBillMutation(
      boqId,
      ({ id, assemblyId }: { id: number; assemblyId: number }) =>
        unwrap(
          api.POST('/api/v1/boq/positions/{position_id}/apply-assembly', {
            ...at(id),
            body: { assembly_id: assemblyId, replace: true },
          })
        )
    ),
    updateBill: useBillMutation(
      boqId,
      (body: components['schemas']['BoqUpdate']) =>
        unwrap(api.PATCH('/api/v1/boq/{boq_id}', { ...path, body }))
    ),
    transition: useBillMutation(
      boqId,
      (body: components['schemas']['BoqTransition']) =>
        unwrap(api.POST('/api/v1/boq/{boq_id}/transition', { ...path, body }))
    ),
    undo: useBillMutation<void>(boqId, () =>
      unwrap(api.POST('/api/v1/boq/{boq_id}/undo', path))
    ),
    redo: useBillMutation<void>(boqId, () =>
      unwrap(api.POST('/api/v1/boq/{boq_id}/redo', path))
    ),
  }
}

export function useValidation(boqId: number, ruleset: Ruleset) {
  return useQuery({
    queryKey: [...keys.validation(boqId), ruleset],
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/boq/{boq_id}/validate', {
          params: { path: { boq_id: boqId }, query: { ruleset } },
        })
      ),
  })
}

export function useResources(params: {
  search?: string
  projectId?: number | null
  type?: ResourceType | null
  page?: number
  perPage?: number
}) {
  const query = {
    search: params.search || undefined,
    project_id: params.projectId ?? undefined,
    type: params.type ?? undefined,
    page: params.page ?? 1,
    items_per_page: params.perPage ?? 100,
  }
  return useQuery({
    queryKey: [...keys.resources, query],
    queryFn: () =>
      unwrap(api.GET('/api/v1/boq/resources/', { params: { query } })),
    placeholderData: keepPreviousData,
  })
}

export function useAssemblies(params: {
  search?: string
  projectId?: number | null
}) {
  const query = {
    search: params.search || undefined,
    project_id: params.projectId ?? undefined,
    items_per_page: 100,
  }
  return useQuery({
    queryKey: [...keys.assemblies, query],
    queryFn: () =>
      unwrap(api.GET('/api/v1/boq/assemblies/', { params: { query } })),
    placeholderData: keepPreviousData,
  })
}

/** POST a file (and form fields) with the CSRF header; returns the parsed JSON or throws its detail. */
export async function upload<T>(
  url: string,
  file: File,
  fields: Record<string, string> = {}
): Promise<T> {
  const form = new FormData()
  form.append('file', file)
  for (const [k, v] of Object.entries(fields)) form.append(k, v)
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
  return body as T
}

export type ImportPreview = {
  columns: string[]
  fields: string[]
  mapping: Record<string, string>
  sample: Record<string, unknown>[]
  rows: number
}

/** Download an export through the browser, keeping the server's file name. */
export async function download(url: string) {
  const response = await fetch(url, { credentials: 'include' })
  if (!response.ok) throw new Error(`Export failed (${response.status})`)
  const blob = await response.blob()
  const name =
    /filename="([^"]+)"/.exec(
      response.headers.get('Content-Disposition') ?? ''
    )?.[1] ?? 'export'
  const href = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = href
  a.download = name
  a.click()
  URL.revokeObjectURL(href)
}

function useInvalidate(key: readonly unknown[]) {
  const queryClient = useQueryClient()
  return () => void queryClient.invalidateQueries({ queryKey: key })
}

export type ResourceBody = Partial<components['schemas']['BoqResourceIn']>

export function useResourceActions() {
  const refresh = useInvalidate(keys.resources)
  const at = (id: number) => ({ params: { path: { resource_id: id } } })
  return {
    refresh,
    create: useMutation({
      mutationFn: (body: ResourceBody) =>
        unwrap(api.POST('/api/v1/boq/resources/', { body: body as never })),
      onSuccess: refresh,
      onError: handleServerError,
    }),
    update: useMutation({
      mutationFn: ({ id, ...body }: ResourceBody & { id: number }) =>
        unwrap(
          api.PATCH('/api/v1/boq/resources/{resource_id}', {
            ...at(id),
            body: body as never,
          })
        ),
      onSuccess: refresh,
      onError: (error) => {
        handleServerError(error)
        refresh()
      },
    }),
    remove: useMutation({
      mutationFn: (id: number) =>
        unwrap(api.DELETE('/api/v1/boq/resources/{resource_id}', at(id))),
      onSuccess: refresh,
      onError: handleServerError,
    }),
  }
}

export type AssemblyBody = Omit<
  components['schemas']['BoqAssemblyIn'],
  'lines'
> & {
  lines: { resource_id: number; factor: string; waste_pct: string }[]
}

export function useAssemblyActions() {
  const refresh = useInvalidate(keys.assemblies)
  return {
    save: useMutation({
      mutationFn: ({ id, ...body }: AssemblyBody & { id?: number }) =>
        id
          ? unwrap(
              api.PUT('/api/v1/boq/assemblies/{assembly_id}', {
                params: { path: { assembly_id: id } },
                body: body as never,
              })
            )
          : unwrap(
              api.POST('/api/v1/boq/assemblies/', { body: body as never })
            ),
      onSuccess: refresh,
      onError: handleServerError,
    }),
    remove: useMutation({
      mutationFn: (id: number) =>
        unwrap(
          api.DELETE('/api/v1/boq/assemblies/{assembly_id}', {
            params: { path: { assembly_id: id } },
          })
        ),
      onSuccess: refresh,
      onError: handleServerError,
    }),
  }
}
