import { useQuery } from '@tanstack/react-query'
import { api, unwrap } from '@/api/client'
import type { components } from '@/api/schema'

export type Rfi = components['schemas']['RfiRead']
export type RfiDetail = components['schemas']['RfiDetail']
export type RfiResponse = components['schemas']['ResponseRead']

export type HistoryEntry = {
  from_status: string | null
  to_status: string
  changed_by_name?: string | null
  note?: string | null
  changed_at: string | null
}

export const PARTIES = [
  'contractor',
  'designer',
  'client',
  'consultant',
  'subcontractor',
] as const
export type Party = (typeof PARTIES)[number]

export const STATUSES = ['draft', 'open', 'answered', 'closed', 'void'] as const
export type RfiStatus = (typeof STATUSES)[number]

/** The moves the backend allows from each status. */
export const NEXT: Record<string, RfiStatus[]> = {
  draft: ['open', 'void'],
  open: ['answered', 'void'],
  answered: ['closed', 'open', 'void'],
  closed: ['void'],
  void: [],
}

export const PRIORITIES = ['critical', 'high', 'medium', 'low'] as const

export const rfiKeys = {
  all: (projectId: number) => ['rfis', projectId] as const,
  one: (id: number) => ['rfis', 'one', id] as const,
  history: (id: number) => ['rfis', 'history', id] as const,
}

export const label = (value: string) =>
  value.replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase())

export function useRfiUsers() {
  return useQuery({
    queryKey: ['rfis', 'users'],
    queryFn: () => unwrap(api.GET('/api/v1/rfis/users')),
    staleTime: 300_000,
  })
}

/** Contacts to address an RFI to; empty for accounts without `contacts.read`. */
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

export function useRfiHistory(id: number) {
  return useQuery({
    queryKey: rfiKeys.history(id),
    queryFn: async () =>
      (await unwrap(
        api.GET('/api/v1/rfis/{rfi_id}/history', {
          params: { path: { rfi_id: id } },
        })
      )) as unknown as HistoryEntry[],
  })
}
