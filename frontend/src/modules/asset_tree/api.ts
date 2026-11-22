import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ApiError, api, csrfHeaders, unwrap } from '@/api/client'
import type { components } from '@/api/schema'
import { handleServerError } from '@/lib/handle-server-error'

type S = components['schemas']
export type Level = S['LevelRead']
export type LevelIn = S['LevelIn']
export type TreeNode = S['NodeRead']
export type NodeUpdate = S['NodeUpdate']
export type Item = S['ItemRead']
export type ItemType = S['ItemTypeRead']
export type Collection = S['CollectionRead']
export type Term = S['AssetTermRead']
export type ImportMapping = S['TreeImportMapping']
export type ImportPreview = S['TreeImportPreview']
export type ImportReport = S['TreeImportReport']
export type MappingProfile = S['MappingProfileRead']

export const ROLES = [
  'grouping',
  'physical',
  'work_anchor',
  'inspection_anchor',
  'progress_unit',
  'schedule_link',
] as const
export const UNIQUENESS = ['per_parent', 'per_level', 'per_project'] as const
export const COLLECTION_KINDS = [
  'job_pack',
  'shutdown_window',
  'test_pack',
  'work_plan',
  'other',
] as const
export const IDENTIFIER_KINDS = ['barcode', 'qr', 'nfc'] as const

export const treeKeys = {
  all: (projectId: number) => ['asset-tree', projectId] as const,
  levels: (projectId: number) => ['asset-tree', projectId, 'levels'] as const,
  types: (projectId: number) => ['asset-tree', projectId, 'types'] as const,
  terms: (projectId: number) => ['asset-tree', projectId, 'terms'] as const,
  children: (projectId: number, parentId: number | null) =>
    ['asset-tree', projectId, 'children', parentId] as const,
  node: (id: number) => ['asset-tree', 'node', id] as const,
}

export function useLevels(projectId: number) {
  return useQuery({
    queryKey: treeKeys.levels(projectId),
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/asset-tree/levels', {
          params: { query: { project_id: projectId } },
        })
      ),
  })
}

export function useItemTypes(projectId: number) {
  return useQuery({
    queryKey: treeKeys.types(projectId),
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/asset-tree/item-types', {
          params: { query: { project_id: projectId } },
        })
      ),
  })
}

export function usePacks() {
  return useQuery({
    queryKey: ['asset-tree', 'packs'],
    queryFn: () =>
      unwrap(api.GET('/api/v1/asset-tree/packs')) as Promise<
        { key: string; title: string; levels: string[] }[]
      >,
  })
}

export function useTermList(projectId: number) {
  return useQuery({
    queryKey: treeKeys.terms(projectId),
    staleTime: 60_000,
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/asset-tree/terminology', {
          params: { query: { project_id: projectId } },
        })
      ),
  })
}

export function useChildren(
  projectId: number,
  parentId: number | null,
  enabled = true,
  includeRetired = false
) {
  return useQuery({
    queryKey: [...treeKeys.children(projectId, parentId), includeRetired],
    enabled,
    queryFn: async () =>
      (
        await unwrap(
          api.GET('/api/v1/asset-tree/nodes/', {
            params: {
              query: {
                project_id: projectId,
                parent_id: parentId ?? undefined,
                include_retired: includeRetired,
                items_per_page: 500,
              },
            },
          })
        )
      ).data,
  })
}

export function useNodeSearch(projectId: number, search: string) {
  return useQuery({
    queryKey: ['asset-tree', projectId, 'search', search],
    enabled: search.trim().length > 0,
    queryFn: async () =>
      (
        await unwrap(
          api.GET('/api/v1/asset-tree/nodes/', {
            params: {
              query: {
                project_id: projectId,
                search: search.trim(),
                items_per_page: 50,
              },
            },
          })
        )
      ).data,
  })
}

export function useNode(id: number | null) {
  return useQuery({
    queryKey: treeKeys.node(id ?? 0),
    enabled: Boolean(id),
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/asset-tree/nodes/{node_id}', {
          params: { path: { node_id: id ?? 0 } },
        })
      ),
  })
}

export function useNodePath(id: number | null) {
  return useQuery({
    queryKey: [...treeKeys.node(id ?? 0), 'path'],
    enabled: Boolean(id),
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/asset-tree/nodes/{node_id}/path', {
          params: { path: { node_id: id ?? 0 } },
        })
      ),
  })
}

export function useItems(
  projectId: number,
  nodeId: number | null,
  itemType: string
) {
  return useQuery({
    queryKey: ['asset-tree', projectId, 'items', nodeId, itemType],
    queryFn: async () =>
      (
        await unwrap(
          api.GET('/api/v1/asset-tree/items/', {
            params: {
              query: {
                project_id: projectId,
                node_id: nodeId ?? undefined,
                item_type_key: itemType || undefined,
                items_per_page: 500,
              },
            },
          })
        )
      ).data,
  })
}

export function useItem(id: number | null) {
  return useQuery({
    queryKey: ['asset-tree', 'item', id],
    enabled: Boolean(id),
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/asset-tree/items/{item_id}', {
          params: { path: { item_id: id ?? 0 } },
        })
      ),
  })
}

export function useCollections(projectId: number) {
  return useQuery({
    queryKey: ['asset-tree', projectId, 'collections'],
    queryFn: async () =>
      (
        await unwrap(
          api.GET('/api/v1/asset-tree/collections/', {
            params: { query: { project_id: projectId, items_per_page: 100 } },
          })
        )
      ).data,
  })
}

export function useProfiles(projectId: number) {
  return useQuery({
    queryKey: ['asset-tree', projectId, 'profiles'],
    queryFn: async () =>
      (
        await unwrap(
          api.GET('/api/v1/asset-tree/mapping-profiles/', {
            params: { query: { project_id: projectId, items_per_page: 100 } },
          })
        )
      ).data,
  })
}

/** Any change to the tree: run it, then refresh everything this project's tree screens show. */
export function useTreeWrite<V, R = unknown>(
  projectId: number,
  call: (v: V) => Promise<R>
) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: call,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: treeKeys.all(projectId) })
      void qc.invalidateQueries({ queryKey: ['asset-tree', 'node'] })
      void qc.invalidateQueries({ queryKey: ['asset-tree', 'item'] })
    },
    onError: handleServerError,
  })
}

export async function lookupItem(projectId: number, value: string) {
  const { data, response } = await api.GET('/api/v1/asset-tree/items/lookup', {
    params: { query: { project_id: projectId, value } },
  })
  if (response.status === 404) return null
  if (!response.ok || !data) throw new ApiError(response.status, null)
  return data
}

export async function postForm<T>(url: string, form: FormData): Promise<T> {
  const response = await fetch(url, {
    method: 'POST',
    credentials: 'include',
    headers: csrfHeaders(),
    body: form,
  })
  const body = await response.json().catch(() => ({}))
  if (!response.ok) throw new ApiError(response.status, body.detail)
  return body as T
}

/** A level's JSONSchema properties as form fields. */
export type SchemaField = {
  key: string
  title: string
  type: 'string' | 'number' | 'integer' | 'boolean' | 'date' | 'enum'
  options?: string[]
}

export function schemaFields(schema: unknown): SchemaField[] {
  const props = (schema as { properties?: Record<string, unknown> })?.properties
  if (!props || typeof props !== 'object') return []
  return Object.entries(props).map(([key, raw]) => {
    const p = (raw ?? {}) as {
      type?: string
      format?: string
      title?: string
      enum?: unknown[]
    }
    const title =
      p.title ?? key.replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase())
    if (Array.isArray(p.enum))
      return { key, title, type: 'enum', options: p.enum.map(String) }
    if (p.format === 'date') return { key, title, type: 'date' }
    if (p.type === 'number' || p.type === 'integer' || p.type === 'boolean')
      return { key, title, type: p.type }
    return { key, title, type: 'string' }
  })
}
