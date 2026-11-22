import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, ApiError, csrfHeaders, unwrap } from '@/api/client'
import type { components } from '@/api/schema'
import { handleServerError } from '@/lib/handle-server-error'

type S = components['schemas']
export type Facility = S['AssetFacilityRead']
export type Floor = S['AssetFloorRead']
export type Space = S['AssetSpaceRead']
export type AssetType = S['AssetTypeRead']
export type Component = S['AssetComponentRead']
export type AssetSystem = S['AssetSystemRead']
export type Tree = S['AssetTree']
export type CobieReport = S['CobieReport']
export type ImportPreview = S['AssetImportPreview']
export type ImportReport = S['AssetImportReport']

export const STATUSES = [
  'planned',
  'installed',
  'commissioned',
  'in_service',
  'decommissioned',
] as const

/** Where the components grid is looking: a node of the tree, or everything. */
export type Place =
  | { kind: 'all' }
  | { kind: 'unplaced' }
  | { kind: 'facility' | 'floor' | 'space'; id: number }

export const keys = {
  all: (projectId: number) => ['assets', projectId] as const,
  tree: (projectId: number) => ['assets', projectId, 'tree'] as const,
  components: (projectId: number, place: Place) =>
    ['assets', projectId, 'components', place] as const,
  types: (projectId: number) => ['assets', projectId, 'types'] as const,
  systems: (projectId: number) => ['assets', projectId, 'systems'] as const,
  spaces: (projectId: number) => ['assets', projectId, 'spaces'] as const,
  cobie: (projectId: number) => ['assets', projectId, 'cobie'] as const,
}

const at = (project_id: number) => ({ path: { project_id } })

/** Every page of a listing. */
async function all<T>(
  fetch: (page: number) => Promise<{ data: T[]; has_more?: boolean }>
): Promise<T[]> {
  const out: T[] = []
  for (let page = 1; ; page++) {
    const res = await fetch(page)
    out.push(...res.data)
    if (!res.has_more) return out
  }
}

export function useTree(projectId: number) {
  return useQuery({
    queryKey: keys.tree(projectId),
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/assets/{project_id}/tree', { params: at(projectId) })
      ),
  })
}

export function useComponents(projectId: number, place: Place) {
  return useQuery({
    queryKey: keys.components(projectId, place),
    queryFn: () =>
      all((page) =>
        unwrap(
          api.GET('/api/v1/assets/{project_id}/components/', {
            params: {
              ...at(projectId),
              query: {
                page,
                items_per_page: 100,
                unplaced: place.kind === 'unplaced' || undefined,
                facility_id: place.kind === 'facility' ? place.id : undefined,
                floor_id: place.kind === 'floor' ? place.id : undefined,
                space_id: place.kind === 'space' ? place.id : undefined,
              },
            },
          })
        )
      ),
  })
}

export function useTypes(projectId: number) {
  return useQuery({
    queryKey: keys.types(projectId),
    queryFn: () =>
      all((page) =>
        unwrap(
          api.GET('/api/v1/assets/{project_id}/types/', {
            params: { ...at(projectId), query: { page, items_per_page: 100 } },
          })
        )
      ),
  })
}

export function useSystems(projectId: number) {
  return useQuery({
    queryKey: keys.systems(projectId),
    queryFn: () =>
      all((page) =>
        unwrap(
          api.GET('/api/v1/assets/{project_id}/systems/', {
            params: { ...at(projectId), query: { page, items_per_page: 100 } },
          })
        )
      ),
  })
}

export function useSpaces(projectId: number) {
  return useQuery({
    queryKey: keys.spaces(projectId),
    queryFn: () =>
      all((page) =>
        unwrap(
          api.GET('/api/v1/assets/{project_id}/spaces/', {
            params: { ...at(projectId), query: { page, items_per_page: 100 } },
          })
        )
      ),
  })
}

export function useContacts(search: string) {
  return useQuery({
    queryKey: ['contacts', 'pick', search],
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/contacts/', {
          params: {
            query: { search: search || undefined, items_per_page: 50 },
          },
        })
      ).then((r) => r.data),
  })
}

export function useRefresh(projectId: number) {
  const queryClient = useQueryClient()
  return () =>
    void queryClient.invalidateQueries({ queryKey: keys.all(projectId) })
}

type Kind =
  | 'facilities'
  | 'floors'
  | 'spaces'
  | 'types'
  | 'systems'
  | 'components'

/** Create, change or delete one row of the register; refreshes the register after. */
export function useWrite(projectId: number) {
  const refresh = useRefresh(projectId)
  return useMutation({
    mutationFn: async ({
      kind,
      id,
      body,
      remove,
    }: {
      kind: Kind
      id?: number
      body?: Record<string, unknown>
      remove?: boolean
    }) => {
      const url = id
        ? `/api/v1/assets/${kind}/${id}`
        : `/api/v1/assets/${projectId}/${kind}/`
      const response = await fetch(url, {
        method: remove ? 'DELETE' : id ? 'PATCH' : 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json', ...csrfHeaders() },
        body: body ? JSON.stringify(body) : undefined,
      })
      const data = await response.json().catch(() => ({}))
      if (!response.ok) {
        const detail = Array.isArray(data.detail)
          ? data.detail.map((d: { msg: string }) => d.msg).join('; ')
          : data.detail
        throw new ApiError(response.status, detail)
      }
      return data as Record<string, unknown>
    },
    onSuccess: refresh,
    onError: (error) => {
      handleServerError(error)
      refresh()
    },
  })
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

export const cobieUrl = (projectId: number) =>
  `/api/v1/assets/${projectId}/cobie.xlsx`
