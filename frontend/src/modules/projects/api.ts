import { useQuery } from '@tanstack/react-query'
import { api, unwrap } from '@/api/client'
import type { components } from '@/api/schema'

export type Project = components['schemas']['ProjectRead']

export const projectKeys = { all: ['projects'] as const }

export function useProjects() {
  return useQuery({
    queryKey: projectKeys.all,
    queryFn: async () =>
      (
        await unwrap(
          api.GET('/api/v1/projects/', {
            params: { query: { items_per_page: 100 } },
          })
        )
      ).data,
  })
}
