import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, unwrap } from '@/api/client'
import type { components } from '@/api/schema'
import { handleServerError } from '@/lib/handle-server-error'

type S = components['schemas']
export type Incident = S['IncidentRead']
export type IncidentCreate = S['IncidentCreate']
export type IncidentUpdate = S['IncidentUpdate']
export type Observation = S['ObservationRead']
export type ObservationCreate = S['ObservationCreate']
export type SafetyAction = S['SafetyActionRead']
export type Hours = S['SafetyHoursRead']
export type Dashboard = S['SafetyDashboard']

export const INCIDENT_TYPES = [
  'injury',
  'near_miss',
  'property_damage',
  'environmental',
  'dangerous_occurrence',
] as const
export const INCIDENT_STATUSES = [
  'reported',
  'investigating',
  'actions_open',
  'closed',
] as const
export const INCIDENT_NEXT: Record<string, string[]> = {
  reported: ['investigating', 'closed'],
  investigating: ['actions_open', 'closed'],
  actions_open: ['closed', 'investigating'],
  closed: ['investigating'],
}
export const CATEGORIES = [
  'ppe',
  'housekeeping',
  'working_at_height',
  'manual_handling',
  'tools_equipment',
  'hot_work',
  'scaffolding',
  'chemicals',
  'permits',
  'behaviour',
  'environmental',
  'other',
] as const
export const ACTION_STATUSES = [
  'open',
  'in_progress',
  'done',
  'verified',
  'cancelled',
] as const

/** Severity × likelihood on the 5×5 matrix: 1-4 low, 5-9 medium, 10-14 high, 15-25 extreme. */
export function band(score: number) {
  if (score >= 15) return 'extreme'
  if (score >= 10) return 'high'
  if (score >= 5) return 'medium'
  return 'low'
}

export const BAND_STYLE: Record<string, string> = {
  low: 'bg-green-500/20 text-green-800 dark:text-green-300',
  medium: 'bg-yellow-400/30 text-yellow-900 dark:text-yellow-200',
  high: 'bg-orange-500/30 text-orange-900 dark:text-orange-200',
  extreme: 'bg-red-600/35 text-red-900 dark:text-red-200',
}

const keys = {
  all: ['safety'] as const,
  incidents: (p: number, type: string, status: string) =>
    ['safety', p, 'incidents', type, status] as const,
  incident: (id: number) => ['safety', 'incident', id] as const,
  observations: (p: number, kind: string) =>
    ['safety', p, 'observations', kind] as const,
  actions: (p: number, parentType: string, parentId: number) =>
    ['safety', p, 'actions', parentType, parentId] as const,
  hours: (p: number) => ['safety', p, 'hours'] as const,
  dashboard: (p: number, base: number | null, from: string, to: string) =>
    ['safety', p, 'dashboard', base, from, to] as const,
}

function useRefresh() {
  const qc = useQueryClient()
  return () => void qc.invalidateQueries({ queryKey: keys.all })
}

export function useIncidents(projectId: number, type: string, status: string) {
  return useQuery({
    queryKey: keys.incidents(projectId, type, status),
    queryFn: async () =>
      (
        await unwrap(
          api.GET('/api/v1/safety/incidents/', {
            params: {
              query: {
                project_id: projectId,
                items_per_page: 100,
                type: (type || undefined) as never,
                status: (status || undefined) as never,
              },
            },
          })
        )
      ).data,
  })
}

export function useIncident(id: number | null) {
  return useQuery({
    queryKey: keys.incident(id ?? 0),
    enabled: Boolean(id),
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/safety/incidents/{incident_id}', {
          params: { path: { incident_id: id ?? 0 } },
        })
      ),
  })
}

export function useIncidentHistory(id: number) {
  return useQuery({
    queryKey: ['safety', 'incident-history', id],
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/safety/incidents/{incident_id}/history', {
          params: { path: { incident_id: id } },
        })
      ) as Promise<
        {
          to_status: string
          changed_by_name: string | null
          note: string | null
          changed_at: string | null
        }[]
      >,
  })
}

export function useReportIncident() {
  const refresh = useRefresh()
  return useMutation({
    mutationFn: (body: IncidentCreate) =>
      unwrap(api.POST('/api/v1/safety/incidents/', { body })),
    onSuccess: refresh,
    onError: handleServerError,
  })
}

export function useUpdateIncident(id: number) {
  const refresh = useRefresh()
  return useMutation({
    mutationFn: (body: IncidentUpdate) =>
      unwrap(
        api.PATCH('/api/v1/safety/incidents/{incident_id}', {
          params: { path: { incident_id: id } },
          body,
        })
      ),
    onSuccess: refresh,
    onError: handleServerError,
  })
}

export function useIncidentStatus(id: number) {
  const refresh = useRefresh()
  return useMutation({
    mutationFn: (body: { status: string; note?: string }) =>
      unwrap(
        api.PATCH('/api/v1/safety/incidents/{incident_id}/status', {
          params: { path: { incident_id: id } },
          body: body as never,
        })
      ),
    onSuccess: refresh,
    onError: handleServerError,
  })
}

export function useObservations(projectId: number, kind: string) {
  return useQuery({
    queryKey: keys.observations(projectId, kind),
    queryFn: async () =>
      (
        await unwrap(
          api.GET('/api/v1/safety/observations/', {
            params: {
              query: {
                project_id: projectId,
                items_per_page: 100,
                kind: (kind || undefined) as never,
              },
            },
          })
        )
      ).data,
  })
}

export function useLogObservation() {
  const refresh = useRefresh()
  return useMutation({
    mutationFn: (body: ObservationCreate) =>
      unwrap(api.POST('/api/v1/safety/observations/', { body })),
    onSuccess: refresh,
    onError: handleServerError,
  })
}

export function useUpdateObservation() {
  const refresh = useRefresh()
  return useMutation({
    mutationFn: ({ id, status }: { id: number; status: 'open' | 'closed' }) =>
      unwrap(
        api.PATCH('/api/v1/safety/observations/{observation_id}', {
          params: { path: { observation_id: id } },
          body: { status },
        })
      ),
    onSuccess: refresh,
    onError: handleServerError,
  })
}

export function useActions(
  projectId: number,
  parentType: 'incident' | 'observation',
  parentId: number
) {
  return useQuery({
    queryKey: keys.actions(projectId, parentType, parentId),
    queryFn: async () =>
      (
        await unwrap(
          api.GET('/api/v1/safety/actions/', {
            params: {
              query: {
                project_id: projectId,
                parent_type: parentType,
                parent_id: parentId,
              },
            },
          })
        )
      ).data,
  })
}

export function useAddAction() {
  const refresh = useRefresh()
  return useMutation({
    mutationFn: (body: S['SafetyActionCreate']) =>
      unwrap(api.POST('/api/v1/safety/actions/', { body })),
    onSuccess: refresh,
    onError: handleServerError,
  })
}

export function useUpdateAction() {
  const refresh = useRefresh()
  return useMutation({
    mutationFn: ({ id, status }: { id: number; status: string }) =>
      unwrap(
        api.PATCH('/api/v1/safety/actions/{action_id}', {
          params: { path: { action_id: id } },
          body: { status: status as never },
        })
      ),
    onSuccess: refresh,
    onError: handleServerError,
  })
}

export function useHours(projectId: number) {
  return useQuery({
    queryKey: keys.hours(projectId),
    queryFn: async () =>
      (
        await unwrap(
          api.GET('/api/v1/safety/hours/', {
            params: { query: { project_id: projectId, items_per_page: 100 } },
          })
        )
      ).data,
  })
}

export function useSetHours() {
  const refresh = useRefresh()
  return useMutation({
    mutationFn: (body: S['SafetyHoursSet']) =>
      unwrap(api.PUT('/api/v1/safety/hours', { body })),
    onSuccess: refresh,
    onError: handleServerError,
  })
}

export function useDeleteHours() {
  const refresh = useRefresh()
  return useMutation({
    mutationFn: (id: number) =>
      unwrap(
        api.DELETE('/api/v1/safety/hours/{hours_id}', {
          params: { path: { hours_id: id } },
        })
      ),
    onSuccess: refresh,
    onError: handleServerError,
  })
}

export function useDashboard(
  projectId: number,
  base: number | null,
  from: string,
  to: string
) {
  return useQuery({
    queryKey: keys.dashboard(projectId, base, from, to),
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/safety/dashboard/{project_id}', {
          params: {
            path: { project_id: projectId },
            query: {
              base: (base ?? undefined) as never,
              date_from: from || undefined,
              date_to: to || undefined,
            },
          },
        })
      ),
  })
}

/** Local date-time for `<input type=datetime-local>`, from now or an ISO string. */
export function localDateTime(iso?: string) {
  const d = iso ? new Date(iso) : new Date()
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}
