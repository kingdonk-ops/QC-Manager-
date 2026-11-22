import { useQuery } from '@tanstack/react-query'
import { api, unwrap } from '@/api/client'
import type { components } from '@/api/schema'

export type Item = components['schemas']['CorrespondenceRead']
export type ThreadEntry = components['schemas']['ThreadEntry']

export type HistoryEntry = {
  from_status: string | null
  to_status: string
  changed_by_name?: string | null
  note?: string | null
  changed_at: string | null
}

export const TYPES = [
  'letter',
  'email',
  'notice',
  'instruction',
  'claim',
  'extension_of_time',
  'other',
] as const

export const STATUSES = [
  'draft',
  'sent',
  'received',
  'response_required',
  'responded',
  'closed',
] as const

/** The moves the backend allows from each status. */
export const NEXT: Record<string, string[]> = {
  draft: ['sent', 'received', 'response_required', 'closed'],
  sent: ['response_required', 'responded', 'closed'],
  received: ['response_required', 'responded', 'closed'],
  response_required: ['responded', 'closed'],
  responded: ['response_required', 'closed'],
  closed: ['response_required'],
}

export const label = (value: string) =>
  value === 'extension_of_time'
    ? 'Extension of time'
    : value.replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase())

export const typeName = (item: Pick<Item, 'type' | 'custom_type'>) =>
  item.custom_type || label(item.type)

export const corKeys = {
  all: (projectId: number) => ['correspondence', projectId] as const,
  one: (id: number) => ['correspondence', 'one', id] as const,
  thread: (id: number) => ['correspondence', 'thread', id] as const,
  history: (id: number) => ['correspondence', 'history', id] as const,
}

/** Contacts for sender and recipients; empty for accounts without `contacts.read`. */
export function useContactOptions() {
  return useQuery({
    queryKey: ['contacts', 'options'],
    queryFn: async () => {
      const { data } = await api.GET('/api/v1/contacts/', {
        params: { query: { items_per_page: 100 } },
      })
      return (data?.data ?? []).map((c) => ({
        id: c.id,
        name: c.company_name
          ? `${c.full_name} (${c.company_name})`
          : c.full_name,
      }))
    },
    staleTime: 300_000,
  })
}

export function useHistory(id: number) {
  return useQuery({
    queryKey: corKeys.history(id),
    queryFn: async () =>
      (await unwrap(
        api.GET('/api/v1/correspondence/{item_id}/history', {
          params: { path: { item_id: id } },
        })
      )) as unknown as HistoryEntry[],
  })
}
