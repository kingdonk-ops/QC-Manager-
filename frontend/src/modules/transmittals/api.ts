import { useQuery } from '@tanstack/react-query'
import { api, unwrap } from '@/api/client'
import type { components } from '@/api/schema'

export type Transmittal = components['schemas']['TransmittalRead']
export type Recipient = components['schemas']['RecipientRead']
export type TransmittalDocument = components['schemas']['DocumentRead']

export const PURPOSES = [
  'for_information',
  'for_review',
  'for_approval',
  'for_construction',
  'as_requested',
] as const

export const label = (value: string) =>
  value.replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase())

export const trKeys = {
  all: (projectId: number) => ['transmittals', projectId] as const,
  one: (id: number) => ['transmittals', 'one', id] as const,
}

export const coverUrl = (id: number) => `/api/v1/transmittals/${id}/cover.pdf`

/** Contacts to send to; empty for accounts without `contacts.read`. */
export function useContactOptions() {
  return useQuery({
    queryKey: ['contacts', 'options', 'with-email'],
    queryFn: async () => {
      const { data } = await api.GET('/api/v1/contacts/', {
        params: { query: { items_per_page: 100 } },
      })
      return (data?.data ?? []).map((c) => ({
        id: c.id,
        name: c.company_name
          ? `${c.full_name} (${c.company_name})`
          : c.full_name,
        email: c.email ?? null,
      }))
    },
    staleTime: 300_000,
  })
}

/** The project's documents, superseded revisions included so they can be flagged. */
export function useProjectDocuments(projectId: number) {
  return useQuery({
    queryKey: ['files', projectId, 'transmittal-picker'],
    queryFn: async () =>
      (
        await unwrap(
          api.GET('/api/v1/files/', {
            params: {
              query: {
                project_id: projectId,
                include_superseded: true,
                items_per_page: 100,
              },
            },
          })
        )
      ).data.filter((f) => !f.entity_type),
  })
}

export function useTransmittal(id: number) {
  return useQuery({
    queryKey: trKeys.one(id),
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/transmittals/{transmittal_id}', {
          params: { path: { transmittal_id: id } },
        })
      ),
  })
}
