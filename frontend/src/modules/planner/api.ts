import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, unwrap } from '@/api/client'
import type { components } from '@/api/schema'
import { handleServerError } from '@/lib/handle-server-error'

type S = components['schemas']
export type Plan = S['PlanRead']
export type PlanIn = S['PlanIn']
export type Pack = S['PackRead']
export type PackIn = S['PackIn']
export type PackUpdate = S['PackUpdate']
export type LineIn = S['PackLineIn']
export type Crew = S['CrewRead']
export type CrewIn = S['CrewIn']
export type Board = S['PlanBoard']
export type Assignment = S['AssignmentRead']
export type Constraint = S['ConstraintRead']
export type ConstraintIn = S['ConstraintIn']
export type PlanVsActual = S['PlanVsActual']
export type Finding = S['ReadinessFindingRead']

export const PLAN_KINDS = [
  'look_ahead',
  'shutdown',
  'campaign',
  'break_in',
  'recovery',
  'other',
] as const
export const PLAN_NEXT: Record<string, string[]> = {
  draft: ['issued', 'cancelled'],
  issued: ['in_execution', 'draft', 'cancelled'],
  in_execution: ['closed', 'cancelled'],
  closed: [],
  cancelled: [],
}
export const PACK_NEXT: Record<string, string[]> = {
  planned: ['ready', 'deferred'],
  ready: ['in_progress', 'planned', 'deferred'],
  in_progress: ['done', 'ready', 'deferred'],
  done: ['in_progress'],
  deferred: ['planned'],
}
export const PREREQ_KINDS = [
  'materials',
  'permit',
  'scaffold',
  'drawings',
  'isolation',
  'inspection',
  'equipment',
  'labour',
  'other',
] as const
export const CONSTRAINT_CATEGORIES = [
  'engineering',
  'materials',
  'scaffold',
  'permits',
  'labour',
  'equipment',
  'preceding',
  'client',
  'weather',
  'other',
] as const

export const plannerKeys = {
  all: ['planner'] as const,
  plans: (projectId: number) => ['planner', 'plans', projectId] as const,
  board: (planId: number) => ['planner', 'board', planId] as const,
  packs: (projectId: number, planId: number) =>
    ['planner', 'packs', projectId, planId] as const,
  pack: (id: number) => ['planner', 'pack', id] as const,
  crews: (projectId: number) => ['planner', 'crews', projectId] as const,
  constraints: (projectId: number, status: string) =>
    ['planner', 'constraints', projectId, status] as const,
  actual: (planId: number) => ['planner', 'actual', planId] as const,
}

function useRefresh() {
  const qc = useQueryClient()
  return () => void qc.invalidateQueries({ queryKey: plannerKeys.all })
}

export function usePlans(projectId: number) {
  return useQuery({
    queryKey: plannerKeys.plans(projectId),
    queryFn: async () =>
      (
        await unwrap(
          api.GET('/api/v1/planner/plans/', {
            params: { query: { project_id: projectId, items_per_page: 100 } },
          })
        )
      ).data,
  })
}

export function useBoard(planId: number | null) {
  return useQuery({
    queryKey: plannerKeys.board(planId ?? 0),
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/planner/plans/{plan_id}/board', {
          params: { path: { plan_id: planId! } },
        })
      ),
    enabled: !!planId,
  })
}

export function usePacks(projectId: number, planId: number | null) {
  return useQuery({
    queryKey: plannerKeys.packs(projectId, planId ?? 0),
    queryFn: async () =>
      (
        await unwrap(
          api.GET('/api/v1/planner/packs/', {
            params: {
              query: {
                project_id: projectId,
                plan_id: planId!,
                items_per_page: 100,
              },
            },
          })
        )
      ).data,
    enabled: !!planId,
  })
}

export function usePack(id: number | null) {
  return useQuery({
    queryKey: plannerKeys.pack(id ?? 0),
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/planner/packs/{pack_id}', {
          params: { path: { pack_id: id! } },
        })
      ),
    enabled: !!id,
  })
}

export function useCrews(projectId: number) {
  return useQuery({
    queryKey: plannerKeys.crews(projectId),
    queryFn: async () =>
      (
        await unwrap(
          api.GET('/api/v1/planner/crews/', {
            params: { query: { project_id: projectId, items_per_page: 100 } },
          })
        )
      ).data,
  })
}

export function useConstraints(projectId: number, status: string) {
  return useQuery({
    queryKey: plannerKeys.constraints(projectId, status),
    queryFn: async () =>
      (
        await unwrap(
          api.GET('/api/v1/planner/constraints/', {
            params: {
              query: {
                project_id: projectId,
                status: (status || undefined) as never,
                items_per_page: 100,
              },
            },
          })
        )
      ).data,
  })
}

export function usePlanVsActual(planId: number | null) {
  return useQuery({
    queryKey: plannerKeys.actual(planId ?? 0),
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/planner/plans/{plan_id}/plan-vs-actual', {
          params: { path: { plan_id: planId! } },
        })
      ),
    enabled: !!planId,
  })
}

/** Every planner write: refreshes all planner queries afterwards. */
export function usePlannerMutation<A, R>(fn: (args: A) => Promise<R>) {
  const refresh = useRefresh()
  return useMutation({
    mutationFn: fn,
    onSuccess: refresh,
    onError: (e) => {
      handleServerError(e)
      refresh()
    },
  })
}

export const plannerApi = {
  createPlan: (body: PlanIn) =>
    unwrap(api.POST('/api/v1/planner/plans/', { body })),
  transitionPlan: ({ id, status }: { id: number; status: string }) =>
    unwrap(
      api.POST('/api/v1/planner/plans/{plan_id}/transition', {
        params: { path: { plan_id: id } },
        body: { status, force: false },
      })
    ),
  createCrew: (body: CrewIn) =>
    unwrap(api.POST('/api/v1/planner/crews/', { body })),
  createPack: (body: PackIn) =>
    unwrap(api.POST('/api/v1/planner/packs/', { body })),
  updatePack: ({ id, body }: { id: number; body: PackUpdate }) =>
    unwrap(
      api.PATCH('/api/v1/planner/packs/{pack_id}', {
        params: { path: { pack_id: id } },
        body,
      })
    ),
  setLines: ({ id, lines }: { id: number; lines: LineIn[] }) =>
    unwrap(
      api.PUT('/api/v1/planner/packs/{pack_id}/lines', {
        params: { path: { pack_id: id } },
        body: { lines },
      })
    ),
  transitionPack: ({
    id,
    status,
    force,
  }: {
    id: number
    status: string
    force?: boolean
  }) =>
    unwrap(
      api.POST('/api/v1/planner/packs/{pack_id}/transition', {
        params: { path: { pack_id: id } },
        body: { status, force: !!force },
      })
    ),
  addPrerequisite: ({
    packId,
    kind,
    description,
  }: {
    packId: number
    kind: string
    description: string
  }) =>
    unwrap(
      api.POST('/api/v1/planner/packs/{pack_id}/prerequisites', {
        params: { path: { pack_id: packId } },
        body: { kind: kind as never, description, status: 'pending' },
      })
    ),
  setPrerequisite: ({ id, status }: { id: number; status: string }) =>
    unwrap(
      api.PATCH('/api/v1/planner/prerequisites/{prereq_id}', {
        params: { path: { prereq_id: id } },
        body: { status: status as never },
      })
    ),
  assign: (body: components['schemas']['AssignmentIn']) =>
    unwrap(api.POST('/api/v1/planner/assignments', { body })),
  unassign: (id: number) =>
    unwrap(
      api.DELETE('/api/v1/planner/assignments/{assignment_id}', {
        params: { path: { assignment_id: id } },
      })
    ),
  createConstraint: (body: ConstraintIn) =>
    unwrap(api.POST('/api/v1/planner/constraints/', { body })),
  resolveConstraint: ({ id, resolution }: { id: number; resolution: string }) =>
    unwrap(
      api.PATCH('/api/v1/planner/constraints/{constraint_id}', {
        params: { path: { constraint_id: id } },
        body: { status: 'resolved', resolution },
      })
    ),
}
