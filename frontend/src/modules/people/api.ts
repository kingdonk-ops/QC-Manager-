import { useQuery } from '@tanstack/react-query'
import { api, unwrap } from '@/api/client'
import type { components } from '@/api/schema'

export type Person = components['schemas']['Person']
export type RoleOption = components['schemas']['RoleOption']

export const peopleKeys = {
  me: ['people', 'me'] as const,
  list: (search: string, inactive: boolean) =>
    ['people', 'list', search, inactive] as const,
  roles: ['people', 'roles'] as const,
}

export function useMyProfile() {
  return useQuery({
    queryKey: peopleKeys.me,
    queryFn: () => unwrap(api.GET('/api/v1/people/me')),
  })
}

export function usePeople(
  search = '',
  includeInactive = false,
  enabled = true
) {
  return useQuery({
    queryKey: peopleKeys.list(search, includeInactive),
    queryFn: async () =>
      (
        await unwrap(
          api.GET('/api/v1/people/', {
            params: {
              query: {
                items_per_page: 100,
                search: search || undefined,
                include_inactive: includeInactive,
              },
            },
          })
        )
      ).data,
    enabled,
  })
}

export function useRoleOptions(enabled = true) {
  return useQuery({
    queryKey: peopleKeys.roles,
    queryFn: () => unwrap(api.GET('/api/v1/people/roles')),
    enabled,
  })
}
