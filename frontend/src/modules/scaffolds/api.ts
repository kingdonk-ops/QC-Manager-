import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, unwrap } from '@/api/client'
import type { components } from '@/api/schema'
import { handleServerError } from '@/lib/handle-server-error'
import { can, useSession } from '@/lib/session'
import { useActiveModules } from '@/modules/_runtime'

type S = components['schemas']
export type LinkedItem = S['TwItemRead']
export type LinkedPermit = S['TwPermitRead']
export type LinkedRollup = S['TwRegisterRollup']
export type Scaffold = S['ScaffoldRead']
export type ScaffoldCreate = S['ScaffoldCreate']
export type ScaffoldUpdate = S['ScaffoldUpdate']
export type Inspection = S['ScaffoldInspectionRead']
export type InspectionCreate = S['ScaffoldInspectionCreate']
export type Modification = S['ModificationRead']
export type Hire = S['HireSummary']

export const STATUSES = [
  'requested',
  'approved',
  'erecting',
  'erected',
  'in_use',
  'modifying',
  'dismantle_requested',
  'dismantling',
  'dismantled',
  'rejected',
  'cancelled',
] as const

export const TYPES = [
  'independent',
  'tower',
  'mobile',
  'birdcage',
  'hanging',
  'cantilever',
  'system',
  'tube_and_fitting',
  'other',
] as const

export const DUTIES = ['light', 'medium', 'heavy', 'special'] as const
export const TAGS = ['green', 'yellow', 'red'] as const
export const INSPECTION_KINDS = [
  'handover',
  'periodic',
  'weather',
  'modification',
  'incident',
  'ad_hoc',
] as const

/** Hand-made steps from each status, and the permission each needs (mirrors the server). */
export const NEXT: Record<string, string[]> = {
  requested: ['approved', 'rejected', 'cancelled'],
  approved: ['erecting', 'cancelled'],
  erecting: ['erected'],
  erected: ['modifying', 'dismantle_requested'],
  in_use: ['modifying', 'dismantle_requested'],
  modifying: ['erected'],
  dismantle_requested: ['dismantling', 'in_use'],
  dismantling: ['dismantled'],
}

export function stepPermission(target: string) {
  if (['approved', 'rejected', 'dismantling'].includes(target))
    return 'scaffolds.approve'
  if (target === 'dismantle_requested') return 'scaffolds.create'
  if (target === 'cancelled') return 'scaffolds.create'
  return 'scaffolds.transition'
}

export const TAG_CLASSES: Record<string, string> = {
  green: 'bg-green-600 text-white',
  yellow: 'bg-yellow-400 text-black',
  red: 'bg-red-600 text-white',
  none: 'bg-muted text-muted-foreground',
}

const keys = {
  all: ['scaffolds'] as const,
  list: (projectId: number, f: object) =>
    ['scaffolds', projectId, 'list', f] as const,
  one: (id: number) => ['scaffolds', 'one', id] as const,
  board: (projectId: number) => ['scaffolds', projectId, 'board'] as const,
  hire: (projectId: number, start: string) =>
    ['scaffolds', projectId, 'hire', start] as const,
}

export function useScaffolds(
  projectId: number,
  f: { status: string; tag: string; search: string; active_only: boolean }
) {
  return useQuery({
    queryKey: keys.list(projectId, f),
    queryFn: async () =>
      (
        await unwrap(
          api.GET('/api/v1/scaffolds/', {
            params: {
              query: {
                project_id: projectId,
                items_per_page: 100,
                status: (f.status || undefined) as never,
                tag: (f.tag || undefined) as never,
                search: f.search || undefined,
                active_only: f.active_only,
              },
            },
          })
        )
      ).data,
  })
}

export function useScaffold(id: number | null) {
  return useQuery({
    queryKey: keys.one(id ?? 0),
    enabled: Boolean(id),
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/scaffolds/{scaffold_id}', {
          params: { path: { scaffold_id: id ?? 0 } },
        })
      ),
  })
}

export function useTagBoard(projectId: number) {
  return useQuery({
    queryKey: keys.board(projectId),
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/scaffolds/tag-board', {
          params: { query: { project_id: projectId } },
        })
      ),
  })
}

export function useHire(projectId: number, start: string) {
  return useQuery({
    queryKey: keys.hire(projectId, start),
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/scaffolds/hire', {
          params: {
            query: { project_id: projectId, start: start || undefined },
          },
        })
      ),
  })
}

export function useInspections(id: number) {
  return useQuery({
    queryKey: ['scaffolds', 'inspections', id],
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/scaffolds/{scaffold_id}/inspections', {
          params: { path: { scaffold_id: id } },
        })
      ),
  })
}

export function useModifications(id: number) {
  return useQuery({
    queryKey: ['scaffolds', 'modifications', id],
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/scaffolds/{scaffold_id}/modifications', {
          params: { path: { scaffold_id: id } },
        })
      ),
  })
}

export function useHistory(id: number) {
  return useQuery({
    queryKey: ['scaffolds', 'history', id],
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/scaffolds/{scaffold_id}/history', {
          params: { path: { scaffold_id: id } },
        })
      ),
  })
}

/** True when the temporary works module is running and the caller may read it. The tab and its query depend on this. */
export function useTemporaryWorksOn() {
  const session = useSession()
  const modules = useActiveModules()
  return (
    can(session, 'temporary_works.read') &&
    modules.some((m) => m.id === 'temporary_works')
  )
}

export type LinkedWorks = {
  items: LinkedItem[]
  permits: LinkedPermit[]
  rollup: LinkedRollup
}

/** The temporary works items linked to a scaffold, with the project's permits and register figures read from the server. */
export function useLinkedWorks(
  projectId: number,
  scaffoldId: number,
  enabled: boolean
) {
  return useQuery({
    queryKey: ['temporary_works', projectId, 'scaffold-link', scaffoldId],
    enabled,
    queryFn: async (): Promise<LinkedWorks> => {
      const project = { project_id: projectId, items_per_page: 100 }
      const [items, permits, rollup] = await Promise.all([
        unwrap(
          api.GET('/api/v1/temporary-works/', {
            params: { query: { ...project, scaffold_id: scaffoldId } },
          })
        ),
        unwrap(
          api.GET('/api/v1/temporary-works/permits/', {
            params: { query: project },
          })
        ),
        unwrap(
          api.GET('/api/v1/temporary-works/register', {
            params: { query: { project_id: projectId } },
          })
        ),
      ])
      return {
        items: (items as { data: LinkedItem[] }).data,
        permits: (permits as { data: LinkedPermit[] }).data,
        rollup,
      }
    },
  })
}

function useWrite<T, R>(call: (v: T) => Promise<R>) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: call,
    onSuccess: () => void qc.invalidateQueries({ queryKey: keys.all }),
    onError: handleServerError,
  })
}

const at = (id: number) => ({ params: { path: { scaffold_id: id } } })

export function useCreateScaffold() {
  return useWrite((body: ScaffoldCreate) =>
    unwrap(api.POST('/api/v1/scaffolds/', { body }))
  )
}

export function useUpdateScaffold(id: number) {
  return useWrite((body: ScaffoldUpdate) =>
    unwrap(api.PATCH('/api/v1/scaffolds/{scaffold_id}', { ...at(id), body }))
  )
}

export function useTransition(id: number) {
  return useWrite((body: { status: string; note?: string; on?: string }) =>
    unwrap(
      api.POST('/api/v1/scaffolds/{scaffold_id}/transition', {
        ...at(id),
        body: body as never,
      })
    )
  )
}

export function useInspect(id: number) {
  return useWrite((body: InspectionCreate) =>
    unwrap(
      api.POST('/api/v1/scaffolds/{scaffold_id}/inspections', {
        ...at(id),
        body,
      })
    )
  )
}

export function useRequestInspection(id: number) {
  return useWrite((body: { reason: string; note?: string }) =>
    unwrap(
      api.POST('/api/v1/scaffolds/{scaffold_id}/inspection-requests', {
        ...at(id),
        body: body as never,
      })
    )
  )
}

export function useRequestModification(id: number) {
  return useWrite((body: { description: string }) =>
    unwrap(
      api.POST('/api/v1/scaffolds/{scaffold_id}/modifications', {
        ...at(id),
        body,
      })
    )
  )
}

export function useDecideModification(id: number) {
  return useWrite(({ modId, status }: { modId: number; status: string }) =>
    unwrap(
      api.POST(
        '/api/v1/scaffolds/{scaffold_id}/modifications/{modification_id}/decision',
        {
          params: { path: { scaffold_id: id, modification_id: modId } },
          body: { status } as never,
        }
      )
    )
  )
}

export function useWeatherEvent() {
  return useWrite(
    (body: { project_id: number; node_id?: number; description: string }) =>
      unwrap(api.POST('/api/v1/scaffolds/weather-events', { body }))
  )
}
