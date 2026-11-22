/** Reading the project's asset hierarchy, for `asset-node-picker`. */
import { useQuery } from '@tanstack/react-query'
import { api, unwrap } from '@/api/client'
import type { components } from '@/api/schema'

export type AssetNode = components['schemas']['NodeRead']

export function useNodes(
  projectId: number,
  parentId: number | null,
  search: string
) {
  return useQuery({
    queryKey: ['asset-tree', 'nodes', projectId, parentId, search],
    queryFn: async () =>
      (
        await unwrap(
          api.GET('/api/v1/asset-tree/nodes/', {
            params: {
              query: {
                project_id: projectId,
                parent_id: search ? undefined : (parentId ?? undefined),
                search: search || undefined,
                items_per_page: 100,
              },
            },
          })
        )
      ).data,
    staleTime: 30_000,
  })
}

/** A node's short label: the display code (e.g. `101 / 101.1`) or its code. */
export function nodeLabel(node: Pick<AssetNode, 'code' | 'display_code'>) {
  return node.display_code || node.code
}
