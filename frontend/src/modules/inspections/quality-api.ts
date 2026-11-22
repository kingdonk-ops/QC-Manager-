/**
 * ITP instances, inspection requests (call-outs), signing, review, competencies and delegations.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, unwrap } from '@/api/client'
import type { components } from '@/api/schema'
import { handleServerError } from '@/lib/handle-server-error'
import { type Inspection, keys as inspectionKeys } from './api'

type S = components['schemas']
export type ItpInstance = S['ItpInstanceRead']
export type ItpLine = S['ItpLineRead']
export type InspectionRequest = S['CalloutRead']
export type RequestParty = S['CalloutPartyRead']
export type RequestBody = S['CalloutCreate']
export type CalendarEvent = S['CalloutCalendarEvent']
export type Signature = S['SignatureRead']
export type Competency = S['CompetencyRead']
export type Delegation = S['DelegationRead']
export type Tiles = S['InspectionDashboard']
export type Finding = S['EligibilityFinding']
export type Points = S['ItpPoints']
export type Activity = S['ItpActivity']

export const PARTIES = ['contractor', 'client', 'third_party'] as const
export const POINTS = ['H', 'W', 'R', 'S', 'none'] as const
export const AREAS = [
  'qa_itp',
  'safety_prestart',
  'equipment_check',
  'repair_fault',
  'health_safety',
  'general',
] as const
export const REQUEST_STATUSES = [
  'draft',
  'requested',
  'confirmed',
  'witnessed',
  'waived',
  'no_show',
  'failed',
  'cancelled',
] as const

export const qkeys = {
  dashboard: (projectId: number) =>
    ['inspections', projectId, 'dashboard'] as const,
  instances: (projectId: number) => ['inspections', projectId, 'itp'] as const,
  instance: (id: number) => ['inspections', 'itp', id] as const,
  requests: (projectId: number, status: string) =>
    ['inspections', projectId, 'requests', status] as const,
  request: (id: number) => ['inspections', 'request', id] as const,
  calendar: (projectId: number, from: string, to: string) =>
    ['inspections', projectId, 'calendar', from, to] as const,
  competencies: (userId: number | null) =>
    ['inspections', 'competencies', userId] as const,
  delegations: (projectId: number) =>
    ['inspections', projectId, 'delegations'] as const,
  pendingCosigns: ['inspections', 'cosigns', 'pending'] as const,
  eligibility: (id: number, action: string) =>
    ['inspections', 'eligibility', id, action] as const,
}

function useInvalidate() {
  const qc = useQueryClient()
  return () => void qc.invalidateQueries({ queryKey: ['inspections'] })
}

// --- dashboard -------------------------------------------------------------------------------

export function useDashboard(projectId: number) {
  return useQuery({
    queryKey: qkeys.dashboard(projectId),
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/inspections/dashboard', {
          params: { query: { project_id: projectId } },
        })
      ),
  })
}

// --- ITP -------------------------------------------------------------------------------------

export function useInstances(projectId: number) {
  return useQuery({
    queryKey: qkeys.instances(projectId),
    queryFn: async () =>
      (
        await unwrap(
          api.GET('/api/v1/inspections/itp/instances/', {
            params: { query: { project_id: projectId, items_per_page: 100 } },
          })
        )
      ).data,
  })
}

export function useInstance(id: number) {
  return useQuery({
    queryKey: qkeys.instance(id),
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/inspections/itp/instances/{instance_id}', {
          params: { path: { instance_id: id } },
        })
      ),
  })
}

export function useApplyItp() {
  const invalidate = useInvalidate()
  return useMutation({
    mutationFn: (body: S['ItpInstanceCreate']) =>
      unwrap(api.POST('/api/v1/inspections/itp/instances', { body })),
    onSuccess: invalidate,
    onError: handleServerError,
  })
}

export function useAnchorOptions(projectId: number) {
  return useQuery({
    queryKey: ['asset-tree', projectId, 'anchor-options'],
    queryFn: async () => {
      const [levels, nodes, items] = await Promise.all([
        unwrap(
          api.GET('/api/v1/asset-tree/levels', {
            params: { query: { project_id: projectId } },
          })
        ),
        unwrap(
          api.GET('/api/v1/asset-tree/nodes/', {
            params: { query: { project_id: projectId, items_per_page: 100 } },
          })
        ),
        unwrap(
          api.GET('/api/v1/asset-tree/items/', {
            params: { query: { project_id: projectId, items_per_page: 100 } },
          })
        ),
      ])
      const anchorLevels = new Set(
        levels
          .filter((l) => (l.roles ?? []).includes('inspection_anchor'))
          .map((l) => l.key)
      )
      return {
        nodes: nodes.data.map((n) => ({
          id: n.id,
          label: n.display_path || n.code,
          anchor: anchorLevels.has(n.level_key),
        })),
        items: items.data.map((i) => ({
          id: i.id,
          label: `${i.tag} (${i.item_type_key})`,
        })),
      }
    },
    retry: false,
  })
}

// --- inspection requests ---------------------------------------------------------------------

export function useRequests(projectId: number, status: string) {
  return useQuery({
    queryKey: qkeys.requests(projectId, status),
    queryFn: async () =>
      (
        await unwrap(
          api.GET('/api/v1/inspections/requests/', {
            params: {
              query: {
                project_id: projectId,
                items_per_page: 100,
                status: (status || undefined) as never,
              },
            },
          })
        )
      ).data,
  })
}

export function useRequest(id: number | null) {
  return useQuery({
    queryKey: qkeys.request(id ?? 0),
    enabled: !!id,
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/inspections/requests/{request_id}', {
          params: { path: { request_id: id ?? 0 } },
        })
      ),
  })
}

export function useCalendar(projectId: number, from: string, to: string) {
  return useQuery({
    queryKey: qkeys.calendar(projectId, from, to),
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/inspections/requests/calendar', {
          params: { query: { project_id: projectId, from, to } },
        })
      ),
  })
}

export function useCreateRequest() {
  const invalidate = useInvalidate()
  return useMutation({
    mutationFn: (body: RequestBody) =>
      unwrap(api.POST('/api/v1/inspections/requests/', { body })),
    onSuccess: invalidate,
    onError: handleServerError,
  })
}

type RequestAction =
  | { action: 'issue' }
  | { action: 'confirm'; body: S['CalloutConfirm'] }
  | { action: 'acknowledge'; body: S['CalloutAcknowledge'] }
  | { action: 'attendance'; body: S['CalloutAttendance'] }
  | { action: 'waive'; body: S['CalloutWaive'] }
  | { action: 'outcome'; body: S['CalloutOutcome'] }
  | { action: 'reschedule'; body: S['CalloutReschedule'] }
  | { action: 'cancel'; body: S['CalloutCancel'] }

export function useRequestAction(id: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (a: RequestAction): Promise<InspectionRequest> => {
      const path = { params: { path: { request_id: id } } }
      switch (a.action) {
        case 'issue':
          return unwrap(
            api.POST('/api/v1/inspections/requests/{request_id}/issue', path)
          )
        case 'confirm':
          return unwrap(
            api.POST('/api/v1/inspections/requests/{request_id}/confirm', {
              ...path,
              body: a.body,
            })
          )
        case 'acknowledge':
          return unwrap(
            api.POST('/api/v1/inspections/requests/{request_id}/acknowledge', {
              ...path,
              body: a.body,
            })
          )
        case 'attendance':
          return unwrap(
            api.POST('/api/v1/inspections/requests/{request_id}/attendance', {
              ...path,
              body: a.body,
            })
          )
        case 'waive':
          return unwrap(
            api.POST('/api/v1/inspections/requests/{request_id}/waive', {
              ...path,
              body: a.body,
            })
          )
        case 'outcome':
          return unwrap(
            api.POST('/api/v1/inspections/requests/{request_id}/outcome', {
              ...path,
              body: a.body,
            })
          )
        case 'reschedule':
          return unwrap(
            api.POST('/api/v1/inspections/requests/{request_id}/reschedule', {
              ...path,
              body: a.body,
            })
          )
        case 'cancel':
          return unwrap(
            api.POST('/api/v1/inspections/requests/{request_id}/cancel', {
              ...path,
              body: a.body,
            })
          )
      }
    },
    onSuccess: (data) => {
      qc.setQueryData(qkeys.request(id), data)
      void qc.invalidateQueries({
        queryKey: ['inspections'],
        predicate: (q) => q.queryKey[1] !== 'request',
      })
    },
    onError: handleServerError,
  })
}

// --- signing and review ----------------------------------------------------------------------

export function useEligibility(id: number, action: string, enabled = true) {
  return useQuery({
    queryKey: qkeys.eligibility(id, action),
    enabled,
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/inspections/{inspection_id}/eligibility', {
          params: { path: { inspection_id: id }, query: { action } },
        })
      ),
  })
}

/** A write that answers with the whole inspection, or a signature (then the inspection is refetched). */
function useSignWrite<T>(id: number, call: (body: T) => Promise<unknown>) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: call,
    onSuccess: (data) => {
      if (data && typeof data === 'object' && 'items' in data)
        qc.setQueryData(inspectionKeys.one(id), data as Inspection)
      void qc.invalidateQueries({ queryKey: ['inspections'] })
    },
    onError: handleServerError,
  })
}

const path = (id: number) => ({ params: { path: { inspection_id: id } } })

export function useSign(id: number) {
  return useSignWrite(id, () =>
    unwrap(
      api.POST('/api/v1/inspections/{inspection_id}/sign', {
        ...path(id),
        body: { accept_intent: true },
      })
    )
  )
}

export function useSubmit(id: number) {
  return useSignWrite(id, (body: S['InspectionSubmit']) =>
    unwrap(
      api.POST('/api/v1/inspections/{inspection_id}/submit', {
        ...path(id),
        body,
      })
    )
  )
}

export function useReview(id: number) {
  return useSignWrite(id, (body: S['InspectionReview']) =>
    unwrap(
      api.POST('/api/v1/inspections/{inspection_id}/review', {
        ...path(id),
        body,
      })
    )
  )
}

export function useCosign(id: number) {
  return useSignWrite(id, (body: S['CosignBody']) =>
    unwrap(
      api.POST('/api/v1/inspections/{inspection_id}/cosign', {
        ...path(id),
        body,
      })
    )
  )
}

export function useDecideCosign(id: number) {
  return useSignWrite(
    id,
    ({
      signatureId,
      body,
    }: {
      signatureId: number
      body: S['CosignDecision']
    }) =>
      unwrap(
        api.POST('/api/v1/inspections/{inspection_id}/cosign/{signature_id}', {
          params: { path: { inspection_id: id, signature_id: signatureId } },
          body,
        })
      )
  )
}

export function useHoldRelease(id: number) {
  return useSignWrite(id, (body: S['HoldReleaseBody']) =>
    unwrap(
      api.POST('/api/v1/inspections/{inspection_id}/hold-release', {
        ...path(id),
        body,
      })
    )
  )
}

export function useResolveComment(id: number) {
  return useSignWrite(id, (commentId: number) =>
    unwrap(
      api.POST(
        '/api/v1/inspections/{inspection_id}/comments/{comment_id}/resolve',
        { params: { path: { inspection_id: id, comment_id: commentId } } }
      )
    )
  )
}

export function usePendingCosigns(enabled: boolean) {
  return useQuery({
    queryKey: qkeys.pendingCosigns,
    enabled,
    queryFn: () => unwrap(api.GET('/api/v1/inspections/cosigns/pending')),
  })
}

// --- competencies and delegations ------------------------------------------------------------

export function useCompetencies(userId: number | null) {
  return useQuery({
    queryKey: qkeys.competencies(userId),
    queryFn: async () =>
      (
        await unwrap(
          api.GET('/api/v1/inspections/competencies/', {
            params: {
              query: { user_id: userId ?? undefined, items_per_page: 100 },
            },
          })
        )
      ).data,
  })
}

export function useSaveCompetency() {
  const invalidate = useInvalidate()
  return useMutation({
    mutationFn: ({
      id,
      body,
    }: {
      id?: number
      body: S['CompetencyIn']
    }): Promise<Competency> => {
      if (id) {
        const { user_id: _, ...rest } = body
        return unwrap(
          api.PATCH('/api/v1/inspections/competencies/{competency_id}', {
            params: { path: { competency_id: id } },
            body: rest,
          })
        )
      }
      return unwrap(api.POST('/api/v1/inspections/competencies/', { body }))
    },
    onSuccess: invalidate,
    onError: handleServerError,
  })
}

export function useDeleteCompetency() {
  const invalidate = useInvalidate()
  return useMutation({
    mutationFn: (id: number) =>
      unwrap(
        api.DELETE('/api/v1/inspections/competencies/{competency_id}', {
          params: { path: { competency_id: id } },
        })
      ),
    onSuccess: invalidate,
    onError: handleServerError,
  })
}

export function useDelegations(projectId: number) {
  return useQuery({
    queryKey: qkeys.delegations(projectId),
    queryFn: async () =>
      (
        await unwrap(
          api.GET('/api/v1/inspections/delegations/', {
            params: { query: { project_id: projectId } },
          })
        )
      ).data,
  })
}

export function useDelegationAction() {
  const invalidate = useInvalidate()
  return useMutation({
    mutationFn: (
      a: { create: S['DelegationIn'] } | { revoke: number }
    ): Promise<Delegation> =>
      'create' in a
        ? unwrap(
            api.POST('/api/v1/inspections/delegations/', { body: a.create })
          )
        : unwrap(
            api.POST('/api/v1/inspections/delegations/{delegation_id}/revoke', {
              params: { path: { delegation_id: a.revoke } },
            })
          ),
    onSuccess: invalidate,
    onError: handleServerError,
  })
}

/** "2026-11-22T09:30" in the browser's zone → an ISO string with offset. */
export function localToIso(value: string): string {
  return new Date(value).toISOString()
}

export function formatWhen(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso)
  return d.toLocaleString(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  })
}

/** The strongest point first: H, W, R, S. */
export function pointTone(point: string): string {
  switch (point) {
    case 'H':
      return 'bg-red-600 text-white'
    case 'W':
      return 'bg-amber-500 text-white'
    case 'R':
      return 'bg-sky-600 text-white'
    case 'S':
      return 'bg-slate-500 text-white'
    default:
      return 'bg-muted text-muted-foreground'
  }
}
