import { useMutation, useQuery } from '@tanstack/react-query'
import { api, unwrap } from '@/api/client'
import type { components } from '@/api/schema'
import { handleServerError } from '@/lib/handle-server-error'

export type Entry = components['schemas']['AuditEntryRead']
export type VerifyResult = components['schemas']['ChainVerifyRead']

export type Filters = {
  entity_type: string
  entity_id: string
  actor_id: string
  action: string
  date_from: string
  date_to: string
  search: string
}

export const EMPTY: Filters = {
  entity_type: '',
  entity_id: '',
  actor_id: '',
  action: '',
  date_from: '',
  date_to: '',
  search: '',
}

/** Only the filters that are set, as query parameters. */
export function query(f: Filters): Record<string, string> {
  return Object.fromEntries(
    Object.entries(f).filter(([, v]) => v.trim() !== '')
  ) as Record<string, string>
}

export function useEntries(f: Filters, page: number) {
  return useQuery({
    queryKey: ['audit', 'entries', f, page],
    placeholderData: (previous) => previous,
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/audit/entries/', {
          params: {
            query: {
              ...query(f),
              actor_id: f.actor_id ? Number(f.actor_id) : undefined,
              page,
              items_per_page: 50,
            } as never,
          },
        })
      ),
  })
}

export function useVerify() {
  return useMutation({
    mutationFn: () => unwrap(api.GET('/api/v1/audit/verify')),
    onError: handleServerError,
  })
}
