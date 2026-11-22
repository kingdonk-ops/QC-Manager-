import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, unwrap } from '@/api/client'
import type { components } from '@/api/schema'
import { handleServerError } from '@/lib/handle-server-error'
import type { FieldDef, IssueType } from './workflow'

type S = components['schemas']
export type Issue = S['NcrRead']
export type IssueAction = S['NcrActionRead']
export type IssueCreate = S['IssueCreate']
export type IssueUpdate = S['IssueUpdate']
export type ActionCreate = S['NcrActionCreate']
export type ActionUpdate = S['NcrActionUpdate']
export type FlagEntry = S['FlagOverrideRead']

export type Revision = {
  id: number
  template_id: number
  number: number
  status: 'draft' | 'published'
  name: string
  fields: FieldDef[]
  notes: string | null
  published_at: string | null
  default_origin: string
  default_visibility: string
  default_mdr_effect: string
  completion_effect: string
  default_severity: string | null
  default_punch_category: string | null
  separate_close: boolean
}

export type Template = {
  id: number
  project_id: number | null
  key: string
  name: string
  issue_type: IssueType
  category: string
  is_active: boolean
  derived_from_id: number | null
  layer: 'library' | 'project'
  published: Revision | null
  draft: Revision | null
  revisions: {
    id: number
    number: number
    status: string
    published_at: string | null
  }[]
}

export type IssueCategory = {
  key: string
  label: string
  is_active: boolean
  sort_order: number
  allows_project_level: boolean
  layer: 'library' | 'project'
}

export type Bucket = {
  open: number
  closed: number
  cat_a_open: number
  cat_b_open: number
  cat_c_open: number
  blocks_mdr: number
}

export type Summary = {
  issue_type: IssueType
  totals: Bucket
  by_category: (Bucket & { category: string })[]
  by_area: (Bucket & { node_id: number | null; label: string })[]
}

export type HistoryRow = {
  from_status: string | null
  to_status: string
  changed_by_name: string | null
  note: string | null
  changed_at: string | null
}

export const SEVERITIES = ['minor', 'major', 'critical'] as const
export const PUNCH_CATEGORIES = ['A', 'B', 'C'] as const
export const ORIGINS = [
  'qa',
  'client',
  'construction',
  'internal_audit',
  'external_audit',
  'supplier',
] as const
export const SOURCES = [
  'walkdown',
  'inspection',
  'audit',
  'client',
  'supplier',
  'other',
] as const
export const ROOT_CAUSES = [
  'workmanship',
  'material',
  'design',
  'procedure',
  'process',
  'equipment',
  'training',
  'subcontractor',
  'supplier',
  'other',
] as const
export const DISPOSITIONS = [
  'rework',
  'repair',
  'use_as_is',
  'scrap',
  'return_to_supplier',
] as const
export const ACTION_STATUSES = [
  'open',
  'in_progress',
  'done',
  'verified',
  'cancelled',
] as const
export const VISIBILITIES = ['internal', 'client'] as const
export const MDR_EFFECTS = ['blocks', 'register_only', 'excluded'] as const
export const COMPLETION_EFFECTS = ['blocks', 'none'] as const

export type Filters = {
  status: string
  category: string
  punch_category: string
  mdr_effect: string
  search: string
  open_only: boolean
}

export const NO_FILTERS: Filters = {
  status: '',
  category: '',
  punch_category: '',
  mdr_effect: '',
  search: '',
  open_only: false,
}

const keys = {
  all: ['issues'] as const,
  list: (projectId: number, type: IssueType, f: Filters) =>
    ['issues', projectId, 'list', type, f] as const,
  summary: (projectId: number, type: IssueType, level: string) =>
    ['issues', projectId, 'summary', type, level] as const,
  one: (id: number) => ['issues', 'one', id] as const,
  history: (id: number) => ['issues', 'history', id] as const,
  flags: (id: number) => ['issues', 'flags', id] as const,
  templates: ['issue-templates'] as const,
}

export function useIssues(projectId: number, type: IssueType, f: Filters) {
  return useQuery({
    queryKey: keys.list(projectId, type, f),
    queryFn: async () =>
      (
        await unwrap(
          api.GET('/api/v1/issues/', {
            params: {
              query: {
                project_id: projectId,
                issue_type: type,
                items_per_page: 100,
                status: (f.status || undefined) as never,
                category: f.category || undefined,
                punch_category: (f.punch_category || undefined) as never,
                mdr_effect: (f.mdr_effect || undefined) as never,
                search: f.search || undefined,
                open_only: f.open_only,
              },
            },
          })
        )
      ).data,
  })
}

export function useSummary(projectId: number, type: IssueType, level: string) {
  return useQuery({
    queryKey: keys.summary(projectId, type, level),
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/issues/summary', {
          params: {
            query: {
              project_id: projectId,
              issue_type: type,
              level_key: level || undefined,
            },
          },
        })
      ) as Promise<Summary>,
  })
}

export function useIssue(id: number | null) {
  return useQuery({
    queryKey: keys.one(id ?? 0),
    enabled: Boolean(id),
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/issues/{issue_id}', {
          params: { path: { issue_id: id ?? 0 } },
        })
      ),
  })
}

export function useIssueHistory(id: number) {
  return useQuery({
    queryKey: keys.history(id),
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/issues/{issue_id}/history', {
          params: { path: { issue_id: id } },
        })
      ) as Promise<HistoryRow[]>,
  })
}

export function useFlagLedger(id: number) {
  return useQuery({
    queryKey: keys.flags(id),
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/issues/{issue_id}/flags', {
          params: { path: { issue_id: id } },
        })
      ),
  })
}

export function useCreateIssue() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: IssueCreate) =>
      unwrap(api.POST('/api/v1/issues/', { body })),
    onSuccess: () => void qc.invalidateQueries({ queryKey: keys.all }),
    onError: handleServerError,
  })
}

/** A write that returns the issue: cache it, refresh lists. */
function useIssueWrite<T>(id: number, call: (v: T) => Promise<Issue>) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: call,
    onSuccess: (data) => {
      qc.setQueryData(keys.one(data.id), data)
      void qc.invalidateQueries({
        queryKey: keys.all,
        predicate: (q) => !(q.queryKey[1] === 'one' && q.queryKey[2] === id),
      })
    },
    onError: handleServerError,
  })
}

const at = (id: number) => ({ params: { path: { issue_id: id } } })
const legacy = (id: number) => ({ params: { path: { ncr_id: id } } })

export function useUpdateIssue(id: number) {
  return useIssueWrite(id, (body: IssueUpdate) =>
    unwrap(api.PATCH('/api/v1/issues/{issue_id}', { ...at(id), body }))
  )
}

export function useTransition(id: number) {
  return useIssueWrite(
    id,
    (body: { to: string; note?: string; attest?: boolean }) =>
      unwrap(
        api.POST('/api/v1/issues/{issue_id}/transition', {
          ...at(id),
          body: body as never,
        })
      )
  )
}

export function useVoid(id: number) {
  return useIssueWrite(id, (reason: string) =>
    unwrap(
      api.POST('/api/v1/issues/{issue_id}/void', {
        ...at(id),
        body: { reason },
      })
    )
  )
}

export function useFlagOverride(id: number) {
  return useIssueWrite(
    id,
    (body: { flag: string; value: string; reason: string }) =>
      unwrap(
        api.POST('/api/v1/issues/{issue_id}/flags', {
          ...at(id),
          body: body as never,
        })
      )
  )
}

export function useUpgrade(id: number) {
  return useIssueWrite(id, (body: { template_id?: number; note?: string }) =>
    unwrap(api.POST('/api/v1/issues/{issue_id}/upgrade', { ...at(id), body }))
  )
}

export function useRaiseExternal(id: number) {
  return useIssueWrite(
    id,
    (body: {
      template_id?: number
      title?: string
      carry_description: boolean
      carry_answers: string[]
      carry_photos: number[]
    }) =>
      unwrap(
        api.POST('/api/v1/issues/{issue_id}/raise-external', {
          ...at(id),
          body,
        })
      )
  )
}

export function useAddAction(id: number) {
  return useIssueWrite(id, (body: ActionCreate) =>
    unwrap(api.POST('/api/v1/ncr/{ncr_id}/actions', { ...legacy(id), body }))
  )
}

export function useUpdateAction(id: number) {
  return useIssueWrite(
    id,
    ({ actionId, body }: { actionId: number; body: ActionUpdate }) =>
      unwrap(
        api.PATCH('/api/v1/ncr/{ncr_id}/actions/{action_id}', {
          params: { path: { ncr_id: id, action_id: actionId } },
          body,
        })
      )
  )
}

export function useDeleteAction(id: number) {
  return useIssueWrite(id, (actionId: number) =>
    unwrap(
      api.DELETE('/api/v1/ncr/{ncr_id}/actions/{action_id}', {
        params: { path: { ncr_id: id, action_id: actionId } },
      })
    )
  )
}

// --- templates ---------------------------------------------------------------------------------

export function useTemplates(
  projectId: number | null,
  type?: IssueType,
  category?: string
) {
  return useQuery({
    queryKey: [...keys.templates, projectId, type, category],
    queryFn: async () =>
      (
        (await unwrap(
          api.GET('/api/v1/issues/templates/', {
            params: {
              query: {
                project_id: projectId ?? undefined,
                issue_type: type,
                category: category || undefined,
              },
            },
          })
        )) as { data: Template[] }
      ).data,
  })
}

export function useTemplate(id: number | null) {
  return useQuery({
    queryKey: [...keys.templates, 'one', id],
    enabled: Boolean(id),
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/issues/templates/{template_id}', {
          params: { path: { template_id: id ?? 0 } },
        })
      ) as Promise<Template>,
  })
}

export function useRevision(id: number | null | undefined) {
  return useQuery({
    queryKey: [...keys.templates, 'revision', id],
    enabled: Boolean(id),
    staleTime: Infinity, // published revisions are frozen
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/issues/template-revisions/{revision_id}', {
          params: { path: { revision_id: id ?? 0 } },
        })
      ) as Promise<Revision>,
  })
}

function useTemplateWrite<T>(call: (v: T) => Promise<unknown>) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (v: T) => (await call(v)) as Template,
    onSuccess: () => void qc.invalidateQueries({ queryKey: keys.templates }),
    onError: handleServerError,
  })
}

export type TemplateBody = {
  project_id?: number | null
  name?: string
  issue_type?: IssueType
  category?: string
  fields?: FieldDef[]
  notes?: string | null
} & Partial<
  Pick<
    Revision,
    | 'default_origin'
    | 'default_visibility'
    | 'default_mdr_effect'
    | 'completion_effect'
    | 'default_severity'
    | 'default_punch_category'
    | 'separate_close'
  >
>

export function useCreateTemplate() {
  return useTemplateWrite((body: TemplateBody) =>
    unwrap(api.POST('/api/v1/issues/templates/', { body: body as never }))
  )
}

export function useSaveDraft(id: number) {
  return useTemplateWrite((body: TemplateBody) =>
    unwrap(
      api.PUT('/api/v1/issues/templates/{template_id}/draft', {
        params: { path: { template_id: id } },
        body: body as never,
      })
    )
  )
}

export function usePublish(id: number) {
  return useTemplateWrite(() =>
    unwrap(
      api.POST('/api/v1/issues/templates/{template_id}/publish', {
        params: { path: { template_id: id } },
      })
    )
  )
}

export function useCopyTemplate(projectId: number) {
  return useTemplateWrite((id: number) =>
    unwrap(
      api.POST('/api/v1/issues/templates/{template_id}/copy', {
        params: { path: { template_id: id }, query: { project_id: projectId } },
      })
    )
  )
}

export function useCategories(projectId: number | null) {
  return useQuery({
    queryKey: [...keys.templates, 'categories', projectId],
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/issues/categories', {
          params: { query: { project_id: projectId ?? undefined } },
        })
      ) as Promise<IssueCategory[]>,
  })
}

export function usePutCategory(projectId: number | null) {
  return useTemplateWrite(
    ({ key, body }: { key: string; body: Partial<IssueCategory> }) =>
      unwrap(
        api.PUT('/api/v1/issues/categories/{key}', {
          params: {
            path: { key },
            query: { project_id: projectId ?? undefined },
          },
          body: body as never,
        })
      )
  )
}

export type DefaultRow = {
  category: string
  issue_type: IssueType
  template_id: number | null
  layer: 'library' | 'project'
}

export function useDefaults(projectId: number | null) {
  return useQuery({
    queryKey: [...keys.templates, 'defaults', projectId],
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/issues/defaults', {
          params: { query: { project_id: projectId ?? undefined } },
        })
      ) as Promise<DefaultRow[]>,
  })
}

export function usePutDefault() {
  return useTemplateWrite(
    (body: {
      project_id: number | null
      category: string
      issue_type: IssueType
      template_id: number
    }) => unwrap(api.PUT('/api/v1/issues/defaults', { body }))
  )
}

// --- anchors ------------------------------------------------------------------------------------

export type NodeOption = { id: number; label: string }

export function useNodeOptions(projectId: number, search: string) {
  return useQuery({
    queryKey: ['asset-tree', projectId, 'node-options', search],
    queryFn: async () => {
      const page = await unwrap(
        api.GET('/api/v1/asset-tree/nodes/', {
          params: {
            query: {
              project_id: projectId,
              search: search || undefined,
              items_per_page: 50,
            },
          },
        })
      )
      return page.data.map(
        (n): NodeOption => ({ id: n.id, label: n.display_path || n.code })
      )
    },
  })
}

export function useContactOptions(enabled: boolean) {
  return useQuery({
    queryKey: ['contacts', 'options'],
    enabled,
    queryFn: async () =>
      (
        await unwrap(
          api.GET('/api/v1/contacts/', {
            params: { query: { items_per_page: 100 } },
          })
        )
      ).data,
  })
}
