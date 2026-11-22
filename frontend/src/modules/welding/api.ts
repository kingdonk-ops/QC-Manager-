import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, unwrap } from '@/api/client'
import type { components } from '@/api/schema'
import { handleServerError } from '@/lib/handle-server-error'

type S = components['schemas']
export type Weld = S['WeldRead']
export type WeldDetail = S['WeldDetail']
export type NdeResult = S['NdeResultRead']
export type NdeRequest = S['NdeRequestRead']
export type Sampling = S['NdeSampling']
export type Welder = S['WelderRead']
export type Matrix = S['QualificationMatrix']
export type Wps = S['WpsRead']
export type Joint = S['BoltedJointRead']
export type JointDetail = S['BoltedJointDetail']
export type RepairRates = S['RepairRates']
export type Drawing = S['WeldDrawingSummary']

export const METHODS = ['rt', 'ut', 'mt', 'pt', 'pmi', 'hardness'] as const
export const JOINT_TYPES = [
  'butt',
  'fillet',
  'socket',
  'branch',
  'seal',
  'other',
] as const
export const CATEGORIES = [
  'normal',
  'category_d',
  'category_m',
  'high_pressure',
  'severe_cyclic',
] as const
export const WELD_STATUSES = [
  'fit_up',
  'welded',
  'nde_pending',
  'accepted',
  'rejected',
  'cut_out',
] as const

/** Matrix cell colour by qualification state. */
export function stateTone(state?: string) {
  if (state === 'valid') return 'bg-green-500/15 text-green-700'
  if (state === 'expiring') return 'bg-amber-500/15 text-amber-700'
  if (state) return 'bg-red-500/15 text-red-700'
  return 'text-muted-foreground'
}

const ROOT = ['welding'] as const

/** A mutation that refreshes every welding query and toasts the backend's refusal. */
export function useAct<V, R = unknown>(fn: (v: V) => Promise<R>) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ROOT }),
    onError: handleServerError,
  })
}

const page = { items_per_page: 100 }

export function useWelds(
  projectId: number,
  filter: { status?: string; drawing_ref?: string; search?: string }
) {
  return useQuery({
    queryKey: [...ROOT, projectId, 'welds', filter],
    queryFn: async () =>
      (
        await unwrap(
          api.GET('/api/v1/welding/welds/', {
            params: {
              query: {
                project_id: projectId,
                ...page,
                status: (filter.status || undefined) as never,
                drawing_ref: filter.drawing_ref || undefined,
                search: filter.search || undefined,
              },
            },
          })
        )
      ).data,
  })
}

export function useWeld(id: number | undefined) {
  return useQuery({
    queryKey: [...ROOT, 'weld', id],
    enabled: !!id,
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/welding/welds/{weld_id}', {
          params: { path: { weld_id: id! } },
        })
      ),
  })
}

export function useDrawings(projectId: number) {
  return useQuery({
    queryKey: [...ROOT, projectId, 'drawings'],
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/welding/drawings', {
          params: { query: { project_id: projectId } },
        })
      ),
  })
}

export function useSampling(projectId: number, method: string) {
  return useQuery({
    queryKey: [...ROOT, projectId, 'sampling', method],
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/welding/sampling', {
          params: { query: { project_id: projectId, method: method as never } },
        })
      ),
  })
}

export function useRequests(projectId: number) {
  return useQuery({
    queryKey: [...ROOT, projectId, 'requests'],
    queryFn: async () =>
      (
        await unwrap(
          api.GET('/api/v1/welding/nde-requests/', {
            params: { query: { project_id: projectId, ...page } },
          })
        )
      ).data,
  })
}

export function usePendingResults(projectId: number) {
  return useQuery({
    queryKey: [...ROOT, projectId, 'pending'],
    queryFn: async () =>
      (
        await unwrap(
          api.GET('/api/v1/welding/nde-results/', {
            params: {
              query: { project_id: projectId, ...page, result: 'pending' },
            },
          })
        )
      ).data,
  })
}

export function useRepairRates(projectId: number) {
  return useQuery({
    queryKey: [...ROOT, projectId, 'rates'],
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/welding/repair-rates', {
          params: { query: { project_id: projectId } },
        })
      ),
  })
}

export function useWelders(projectId: number) {
  return useQuery({
    queryKey: [...ROOT, projectId, 'welders'],
    queryFn: async () =>
      (
        await unwrap(
          api.GET('/api/v1/welding/welders/', {
            params: { query: { project_id: projectId, ...page } },
          })
        )
      ).data,
  })
}

export function useMatrix(projectId: number) {
  return useQuery({
    queryKey: [...ROOT, projectId, 'matrix'],
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/welding/qualification-matrix', {
          params: { query: { project_id: projectId } },
        })
      ),
  })
}

export function useWps(projectId: number) {
  return useQuery({
    queryKey: [...ROOT, projectId, 'wps'],
    queryFn: async () =>
      (
        await unwrap(
          api.GET('/api/v1/welding/wps/', {
            params: { query: { project_id: projectId, ...page } },
          })
        )
      ).data,
  })
}

export function useJoints(projectId: number) {
  return useQuery({
    queryKey: [...ROOT, projectId, 'joints'],
    queryFn: async () =>
      (
        await unwrap(
          api.GET('/api/v1/welding/joints/', {
            params: { query: { project_id: projectId, ...page } },
          })
        )
      ).data,
  })
}

export function useJoint(id: number | undefined) {
  return useQuery({
    queryKey: [...ROOT, 'joint', id],
    enabled: !!id,
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/welding/joints/{joint_id}', {
          params: { path: { joint_id: id! } },
        })
      ),
  })
}

/** Equipment usable today, for the make-up tool picker (empty when calibration is off or not readable). */
export function useUsableTools(projectId: number) {
  return useQuery({
    queryKey: [...ROOT, projectId, 'tools'],
    retry: false,
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/calibration/available', {
          params: { query: { project_id: projectId } },
        })
      ).catch(() => []),
  })
}

/** Work-anchor and other nodes by text, for pickers. */
export function useNodeSearch(projectId: number, search: string) {
  return useQuery({
    queryKey: ['asset-tree', projectId, 'node-search', search],
    enabled: search.length > 0,
    queryFn: async () =>
      (
        await unwrap(
          api.GET('/api/v1/asset-tree/nodes/', {
            params: {
              query: { project_id: projectId, search, items_per_page: 20 },
            },
          })
        )
      ).data,
  })
}

export const weldingApi = {
  createWeld: (body: S['WeldIn']) =>
    unwrap(api.POST('/api/v1/welding/welds/', { body })),
  recordWelding: (id: number, body: S['WeldingIn']) =>
    unwrap(
      api.POST('/api/v1/welding/welds/{weld_id}/weld', {
        params: { path: { weld_id: id } },
        body,
      })
    ),
  visual: (id: number, result: 'accepted' | 'rejected') =>
    unwrap(
      api.POST('/api/v1/welding/welds/{weld_id}/visual', {
        params: { path: { weld_id: id } },
        body: { result },
      })
    ),
  pwht: (id: number, done_on: string) =>
    unwrap(
      api.POST('/api/v1/welding/welds/{weld_id}/pwht', {
        params: { path: { weld_id: id } },
        body: { done_on },
      })
    ),
  repair: (id: number, body: S['WeldRepairIn']) =>
    unwrap(
      api.POST('/api/v1/welding/welds/{weld_id}/repairs', {
        params: { path: { weld_id: id } },
        body,
      })
    ),
  accept: (id: number) =>
    unwrap(
      api.POST('/api/v1/welding/welds/{weld_id}/accept', {
        params: { path: { weld_id: id } },
        body: {},
      })
    ),
  cutOut: (id: number) =>
    unwrap(
      api.POST('/api/v1/welding/welds/{weld_id}/cut-out', {
        params: { path: { weld_id: id } },
        body: {},
      })
    ),
  createRequest: (body: S['NdeRequestIn']) =>
    unwrap(api.POST('/api/v1/welding/nde-requests/', { body })),
  recordResult: (id: number, body: S['NdeResultIn']) =>
    unwrap(
      api.POST('/api/v1/welding/nde-results/{result_id}', {
        params: { path: { result_id: id } },
        body,
      })
    ),
  createWelder: (body: S['WelderIn']) =>
    unwrap(api.POST('/api/v1/welding/welders/', { body })),
  addQualification: (id: number, body: S['QualificationIn']) =>
    unwrap(
      api.POST('/api/v1/welding/welders/{welder_id}/qualifications', {
        params: { path: { welder_id: id } },
        body,
      })
    ),
  createWps: (body: S['WpsIn']) =>
    unwrap(api.POST('/api/v1/welding/wps/', { body })),
  wpsStatus: (id: number, status: 'approved' | 'withdrawn' | 'draft') =>
    unwrap(
      api.POST('/api/v1/welding/wps/{wps_id}/status', {
        params: { path: { wps_id: id } },
        body: { status },
      })
    ),
  createJoint: (body: S['BoltedJointIn']) =>
    unwrap(api.POST('/api/v1/welding/joints/', { body })),
  jointEvent: (id: number, body: S['BoltedJointEventIn']) =>
    unwrap(
      api.POST('/api/v1/welding/joints/{joint_id}/events', {
        params: { path: { joint_id: id } },
        body,
      })
    ),
}
