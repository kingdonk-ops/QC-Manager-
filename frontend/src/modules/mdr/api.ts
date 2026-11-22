import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, unwrap } from '@/api/client'
import type { components } from '@/api/schema'
import { handleServerError } from '@/lib/handle-server-error'

type S = components['schemas']
export type Dossier = S['DossierRead']
export type DossierUpdate = S['DossierUpdate']
export type Revision = S['RevisionRead']
export type Gate = S['GateRead']
export type CatalogueEntry = S['CatalogueRead']
export type TreeNode = S['NodeRead']
export type Collection = S['CollectionRead']

const keys = {
  all: ['mdr'] as const,
  list: (projectId: number) => ['mdr', projectId, 'list'] as const,
  one: (id: number) => ['mdr', 'one', id] as const,
}

export function useDossiers(projectId: number) {
  return useQuery({
    queryKey: keys.list(projectId),
    queryFn: async () =>
      (
        await unwrap(
          api.GET('/api/v1/mdr/dossiers/', {
            params: { query: { project_id: projectId, items_per_page: 100 } },
          })
        )
      ).data,
  })
}

export function useDossier(id: number | null) {
  return useQuery({
    queryKey: keys.one(id ?? 0),
    enabled: Boolean(id),
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/mdr/dossiers/{dossier_id}', {
          params: { path: { dossier_id: id ?? 0 } },
        })
      ),
  })
}

export function useCatalogue(projectId: number) {
  return useQuery({
    queryKey: ['mdr', projectId, 'sections'],
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/mdr/sections', {
          params: { query: { project_id: projectId } },
        })
      ),
  })
}

export function useGate(id: number, purpose: string) {
  return useQuery({
    queryKey: ['mdr', 'one', id, 'gate', purpose],
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/mdr/dossiers/{dossier_id}/gate', {
          params: {
            path: { dossier_id: id },
            query: { purpose: purpose || undefined },
          },
        })
      ),
  })
}

export function useRevisions(id: number) {
  return useQuery({
    queryKey: ['mdr', 'one', id, 'revisions'],
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/mdr/dossiers/{dossier_id}/revisions', {
          params: { path: { dossier_id: id } },
        })
      ),
  })
}

export function useHistory(id: number) {
  return useQuery({
    queryKey: ['mdr', 'one', id, 'history'],
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/mdr/dossiers/{dossier_id}/history', {
          params: { path: { dossier_id: id } },
        })
      ) as Promise<
        {
          from_status: string | null
          to_status: string
          note: string | null
          changed_at: string | null
        }[]
      >,
  })
}

function useWrite<T, R>(call: (v: T) => Promise<R>) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: call,
    onSuccess: () => void qc.invalidateQueries({ queryKey: keys.all }),
    onError: handleServerError,
  })
}

export function useCreateDossier() {
  return useWrite((body: S['DossierIn']) =>
    unwrap(api.POST('/api/v1/mdr/dossiers/', { body }))
  )
}

export function useUpdateDossier(id: number) {
  return useWrite((body: DossierUpdate) =>
    unwrap(
      api.PATCH('/api/v1/mdr/dossiers/{dossier_id}', {
        params: { path: { dossier_id: id } },
        body,
      })
    )
  )
}

export function useDraft(id: number) {
  return useWrite(() =>
    unwrap(
      api.POST('/api/v1/mdr/dossiers/{dossier_id}/draft', {
        params: { path: { dossier_id: id } },
      })
    )
  )
}

export function useIssue(id: number) {
  return useWrite((purpose: 'review' | 'final') =>
    unwrap(
      api.POST('/api/v1/mdr/dossiers/{dossier_id}/issue', {
        params: { path: { dossier_id: id } },
        body: { purpose },
      })
    )
  )
}

export function useSign() {
  return useWrite((revisionId: number) =>
    unwrap(
      api.POST('/api/v1/mdr/revisions/{revision_id}/sign', {
        params: { path: { revision_id: revisionId } },
        body: { confirm: true },
      })
    )
  )
}

export function useDecide() {
  return useWrite(
    ({
      revisionId,
      decision,
      note,
    }: {
      revisionId: number
      decision: 'accepted' | 'rejected'
      note?: string
    }) =>
      unwrap(
        api.POST('/api/v1/mdr/revisions/{revision_id}/decision', {
          params: { path: { revision_id: revisionId } },
          body: { decision, note: note || null },
        })
      )
  )
}

export function useVerifyHash(id: number) {
  return useMutation({
    mutationFn: (sha256: string) =>
      unwrap(
        api.POST('/api/v1/mdr/dossiers/{dossier_id}/verify-hash', {
          params: { path: { dossier_id: id } },
          body: { sha256 },
        })
      ),
    onError: handleServerError,
  })
}

export function useTreeChildren(projectId: number, parentId: number | null) {
  return useQuery({
    queryKey: ['asset-tree', projectId, 'children', parentId],
    queryFn: async () =>
      (
        await unwrap(
          api.GET('/api/v1/asset-tree/nodes/', {
            params: {
              query: {
                project_id: projectId,
                parent_id: parentId ?? undefined,
                items_per_page: 100,
              },
            },
          })
        )
      ).data,
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

export const downloadUrl = (revisionId: number) =>
  `/api/v1/mdr/revisions/${revisionId}/download`
