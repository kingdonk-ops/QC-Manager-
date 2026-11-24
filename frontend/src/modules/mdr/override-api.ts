/** The dossier issue override: record one, and read the history. The server decides what may be covered. */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ApiError, api, unwrap } from '@/api/client'
import type { components } from '@/api/schema'

type S = components['schemas']
export type Override = S['OverrideRead']
export type OverrideBody = S['OverrideIn']
export type GateCountsRead = S['GateCounts']

export const SEVERITIES = ['minor', 'major', 'critical'] as const

export type Blocker = { key: string; title: string; messages: string[] }

const toBlocker = (c: S['CheckRead']): Blocker => ({
  key: c.key,
  title: c.title,
  messages: c.findings.map((f) => f.message),
})

const failing = (c: S['CheckRead']) => c.blocking && c.status === 'fail'

/** The failing blocking checks an override may cover, shown in the dialog as the blockers to cover. */
export function blockersOf(checks: S['CheckRead'][]): Blocker[] {
  return checks.filter((c) => failing(c) && c.overridable).map(toBlocker)
}

/** The failing blocking checks the server says can never be overridden; while any fails no override can be recorded. */
export function unoverridableOf(checks: S['CheckRead'][]): Blocker[] {
  return checks.filter((c) => failing(c) && !c.overridable).map(toBlocker)
}

/** The server's refusal text for a failed request, as it came. */
export function refusalText(error: unknown): string {
  if (error instanceof ApiError && typeof error.detail === 'string')
    return error.detail
  if (error instanceof Error && error.message) return error.message
  return 'Something went wrong!'
}

export function useOverrides(dossierId: number) {
  return useQuery({
    queryKey: ['mdr', 'one', dossierId, 'overrides'],
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/mdr/dossiers/{dossier_id}/overrides', {
          params: { path: { dossier_id: dossierId } },
        })
      ),
  })
}

/** Records an override; refusals are shown by the dialog, not toasted. Holds, checks and counts are refreshed after. */
export function useRecordOverride(dossierId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: OverrideBody) =>
      unwrap(
        api.POST('/api/v1/mdr/dossiers/{dossier_id}/override', {
          params: { path: { dossier_id: dossierId } },
          body,
        })
      ),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['mdr'] })
      void qc.invalidateQueries({ queryKey: ['inspections'] })
    },
  })
}
