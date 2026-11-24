import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ApiError, api, unwrap } from '@/api/client'
import type { components } from '@/api/schema'
import { handleServerError } from '@/lib/handle-server-error'

type S = components['schemas']
export type Item = S['TwItemRead']
export type ItemWrite = S['TwItemWriteRead']
export type ItemCreate = S['TwItemCreate']
export type ItemUpdate = S['TwItemUpdate']
export type Permit = S['TwPermitRead']
export type PermitWrite = S['TwPermitWriteRead']
export type PermitCreate = S['TwPermitCreate']
export type PermitUpdate = S['TwPermitUpdate']
export type Rollup = S['TwRegisterRollup']
export type LoadStatus = S['TwLoadStatusRead']
export type History = S['TwHistoryRead']
export type Finding = S['TwFindingRead']
export type Breach = S['TwBreachRead']
export type DeletedItem = S['TwDeletedItemRead']
export type DeletedPermit = S['TwDeletedPermitRead']
export type Retention = S['TwRetentionRead']

/** The answer to a delete: which place the record went to (the recycle bin or the Deleted folder). */
export type Deleted = { message: string; destination: string }

/** A page of records with the total the server counted. */
export type Listed<T> = { rows: T[]; total: number }

export type TrashView = 'bin' | 'deleted'

const MAX_PAGE = 100

export const keys = {
  all: ['temporary_works'] as const,
  items: (projectId: number, scaffoldId?: number) =>
    ['temporary_works', projectId, 'items', scaffoldId ?? null] as const,
  permits: (projectId: number) =>
    ['temporary_works', projectId, 'permits'] as const,
  rollup: (projectId: number) =>
    ['temporary_works', projectId, 'rollup'] as const,
  loadStatus: (projectId: number) =>
    ['temporary_works', projectId, 'load-status'] as const,
  history: (kind: string, id: number) =>
    ['temporary_works', 'history', kind, id] as const,
  trash: (projectId: number, view: TrashView, kind: string) =>
    ['temporary_works', projectId, 'trash', view, kind] as const,
  retention: (projectId: number) =>
    ['temporary_works', projectId, 'retention'] as const,
  scaffolds: (projectId: number) =>
    ['temporary_works', projectId, 'scaffold-picker'] as const,
}

type Page<T> = { data: T[]; total_count: number }

/** A refusal as text: the server's detail verbatim (a list of problems is joined, not parsed). */
export function refusalText(error: unknown): string {
  if (error instanceof ApiError) {
    const d = error.detail
    if (typeof d === 'string') return d
    if (Array.isArray(d))
      return d
        .map((p) =>
          p && typeof p === 'object' && 'msg' in p
            ? String((p as { msg: unknown }).msg)
            : String(p)
        )
        .join('; ')
    return error.message
  }
  return error instanceof Error ? error.message : String(error)
}

export function useItems(projectId: number, scaffoldId?: number) {
  return useQuery({
    queryKey: keys.items(projectId, scaffoldId),
    enabled: projectId > 0,
    queryFn: async (): Promise<Listed<Item>> => {
      const page = (await unwrap(
        api.GET('/api/v1/temporary-works/', {
          params: {
            query: {
              project_id: projectId,
              items_per_page: MAX_PAGE,
              scaffold_id: scaffoldId,
            },
          },
        })
      )) as Page<Item>
      return { rows: page.data, total: page.total_count }
    },
  })
}

export function usePermits(projectId: number) {
  return useQuery({
    queryKey: keys.permits(projectId),
    queryFn: async (): Promise<Listed<Permit>> => {
      const page = (await unwrap(
        api.GET('/api/v1/temporary-works/permits/', {
          params: {
            query: { project_id: projectId, items_per_page: MAX_PAGE },
          },
        })
      )) as Page<Permit>
      return { rows: page.data, total: page.total_count }
    },
  })
}

export function useRollup(projectId: number) {
  return useQuery({
    queryKey: keys.rollup(projectId),
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/temporary-works/register', {
          params: { query: { project_id: projectId } },
        })
      ),
  })
}

export function useLoadStatus(projectId: number) {
  return useQuery({
    queryKey: keys.loadStatus(projectId),
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/temporary-works/load-status', {
          params: { query: { project_id: projectId } },
        })
      ),
  })
}

export function useItemHistory(id: number | null) {
  return useQuery({
    queryKey: keys.history('item', id ?? 0),
    enabled: Boolean(id),
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/temporary-works/{item_id}/history', {
          params: { path: { item_id: id ?? 0 } },
        })
      ),
  })
}

export function usePermitHistory(id: number | null) {
  return useQuery({
    queryKey: keys.history('permit', id ?? 0),
    enabled: Boolean(id),
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/temporary-works/permits/{permit_id}/history', {
          params: { path: { permit_id: id ?? 0 } },
        })
      ),
  })
}

/** The project's scaffolds, for the scaffold picker of the item form. */
export function useScaffoldPicker(projectId: number, enabled: boolean) {
  return useQuery({
    queryKey: keys.scaffolds(projectId),
    enabled,
    queryFn: async () =>
      (
        (await unwrap(
          api.GET('/api/v1/scaffolds/', {
            params: {
              query: { project_id: projectId, items_per_page: MAX_PAGE },
            },
          })
        )) as Page<{ id: number; code: string; node_path?: string | null }>
      ).data,
  })
}

/** A write. Every temporary works query is refreshed afterwards; `quiet` leaves the error to the caller to show. */
function useWrite<T, R>(call: (v: T) => Promise<R>, quiet = false) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: call,
    onSuccess: () => void qc.invalidateQueries({ queryKey: keys.all }),
    onError: quiet ? undefined : handleServerError,
  })
}

const item = (id: number) => ({ params: { path: { item_id: id } } })
const permit = (id: number) => ({ params: { path: { permit_id: id } } })

export function useCreateItem() {
  return useWrite((body: ItemCreate) =>
    unwrap(api.POST('/api/v1/temporary-works/', { body }))
  )
}

export function useUpdateItem(id: number) {
  return useWrite((body: ItemUpdate) =>
    unwrap(
      api.PATCH('/api/v1/temporary-works/{item_id}', { ...item(id), body })
    )
  )
}

/** Moves an item along its guarded flow. The refusal is shown by the dialog, word for word. */
export function useTransitionItem(id: number) {
  return useWrite(
    (body: { status: string; note?: string | null }) =>
      unwrap(
        api.POST('/api/v1/temporary-works/{item_id}/transition', {
          ...item(id),
          body: body as never,
        })
      ),
    true
  )
}

export function useReturnItem(id: number) {
  return useWrite(
    (body: { reason: string }) =>
      unwrap(
        api.POST('/api/v1/temporary-works/{item_id}/return-to-draft', {
          ...item(id),
          body,
        })
      ),
    true
  )
}

export function useDeleteItem(id: number) {
  return useWrite(
    async () =>
      (await unwrap(
        api.DELETE('/api/v1/temporary-works/{item_id}', item(id))
      )) as Deleted,
    true
  )
}

export function useCreatePermit(itemId: number) {
  return useWrite((body: PermitCreate) =>
    unwrap(
      api.POST('/api/v1/temporary-works/permits/', {
        params: { query: { item_id: itemId } },
        body,
      })
    )
  )
}

export function useUpdatePermit(id: number) {
  return useWrite((body: PermitUpdate) =>
    unwrap(
      api.PATCH('/api/v1/temporary-works/permits/{permit_id}', {
        ...permit(id),
        body,
      })
    )
  )
}

export type PermitStep = 'issue' | 'activate' | 'close'

/** Issue, activate or close a permit. The refusal (one error per missing prerequisite) is shown by the caller. */
export function usePermitStep() {
  return useWrite(
    async ({ id, step }: { id: number; step: PermitStep }) => {
      const at = permit(id)
      if (step === 'issue')
        return unwrap(
          api.POST('/api/v1/temporary-works/permits/{permit_id}/issue', at)
        )
      if (step === 'activate')
        return unwrap(
          api.POST('/api/v1/temporary-works/permits/{permit_id}/activate', at)
        )
      return unwrap(
        api.POST('/api/v1/temporary-works/permits/{permit_id}/close', at)
      )
    },
    true
  )
}

export function useReturnPermit(id: number) {
  return useWrite(
    (body: { reason: string }) =>
      unwrap(
        api.POST('/api/v1/temporary-works/permits/{permit_id}/return-to-draft', {
          ...permit(id),
          body,
        })
      ),
    true
  )
}

export function useDeletePermit(id: number) {
  return useWrite(
    async () =>
      (await unwrap(
        api.DELETE('/api/v1/temporary-works/permits/{permit_id}', permit(id))
      )) as Deleted,
    true
  )
}

/** The recycle bin or the Deleted folder: deleted items or deleted permits. Needs the restore permission. */
export function useTrashItems(projectId: number, view: TrashView) {
  return useQuery({
    queryKey: keys.trash(projectId, view, 'items'),
    queryFn: async (): Promise<Listed<DeletedItem>> => {
      const page = (await unwrap(
        api.GET('/api/v1/temporary-works/trash/{view}/items', {
          params: {
            path: { view } as never,
            query: { project_id: projectId, items_per_page: MAX_PAGE },
          },
        })
      )) as Page<DeletedItem>
      return { rows: page.data, total: page.total_count }
    },
  })
}

export function useTrashPermits(projectId: number, view: TrashView) {
  return useQuery({
    queryKey: keys.trash(projectId, view, 'permits'),
    queryFn: async (): Promise<Listed<DeletedPermit>> => {
      const page = (await unwrap(
        api.GET('/api/v1/temporary-works/trash/{view}/permits', {
          params: {
            path: { view } as never,
            query: { project_id: projectId, items_per_page: MAX_PAGE },
          },
        })
      )) as Page<DeletedPermit>
      return { rows: page.data, total: page.total_count }
    },
  })
}

export function useRestoreItem() {
  return useWrite((id: number) =>
    unwrap(
      api.POST('/api/v1/temporary-works/trash/items/{item_id}/restore', {
        ...item(id),
      })
    )
  )
}

export function useRestorePermit() {
  return useWrite((id: number) =>
    unwrap(
      api.POST('/api/v1/temporary-works/trash/permits/{permit_id}/restore', {
        ...permit(id),
      })
    )
  )
}

export function useRetention(projectId: number) {
  return useQuery({
    queryKey: keys.retention(projectId),
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/temporary-works/trash/settings', {
          params: { query: { project_id: projectId } },
        })
      ),
  })
}

export function useSetRetention() {
  return useWrite((body: { project_id: number; bin_retention_days: number }) =>
    unwrap(api.PUT('/api/v1/temporary-works/trash/settings', { body }))
  )
}
