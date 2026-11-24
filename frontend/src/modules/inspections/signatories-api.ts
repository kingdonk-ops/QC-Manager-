/**
 * Distinct signers on an ITP line: the server's status read and the additional-signatory action.
 * The client only shows what the server answers; it never counts signers itself.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ApiError, api, unwrap } from '@/api/client'
import type { components } from '@/api/schema'

type S = components['schemas']
export type SignatoryStatus = S['SignatoryStatus']
export type SignatoryPerson = S['SignatoryPerson']

export const REQUIRED_MIN = 1
export const REQUIRED_MAX = 10

export const signatoryKeys = {
  one: (id: number) => ['inspections', 'signatories', id] as const,
}

/** A typed required count: a whole number from 1 to 10, or null when it is not one. Empty is not parsed here. */
export function parseRequired(text: string): number | null {
  const trimmed = text.trim()
  if (!/^\d+$/.test(trimmed)) return null
  const n = Number(trimmed)
  return n >= REQUIRED_MIN && n <= REQUIRED_MAX ? n : null
}

/** The server's refusal text for a failed request, as it came. */
export function refusalText(error: unknown): string {
  if (error instanceof ApiError && typeof error.detail === 'string')
    return error.detail
  if (error instanceof Error && error.message) return error.message
  return 'Something went wrong!'
}

/** Required, collected, who signed and whether the requirement is met, for one ITP line. */
export function useSignatories(id: number, enabled = true) {
  return useQuery({
    queryKey: signatoryKeys.one(id),
    enabled,
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/inspections/{inspection_id}/signatories', {
          params: { path: { inspection_id: id } },
        })
      ),
  })
}

/** Adds the caller's signature as an additional signatory; refusals are shown by the dialog, not toasted. */
export function useAddSignatory(id: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () =>
      unwrap(
        api.POST('/api/v1/inspections/{inspection_id}/signatories/additional', {
          params: { path: { inspection_id: id } },
          body: { accept_intent: true },
        })
      ),
    onSuccess: (status) => {
      qc.setQueryData(signatoryKeys.one(id), status)
      void qc.invalidateQueries({ queryKey: ['inspections'] })
    },
  })
}
