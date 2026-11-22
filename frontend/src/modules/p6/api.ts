import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { allPages } from '@/api/all-pages'
import { ApiError, api, csrfHeaders, unwrap } from '@/api/client'
import type { components } from '@/api/schema'
import { handleServerError } from '@/lib/handle-server-error'

export type P6Import = components['schemas']['P6ImportRead']
export type P6Change = components['schemas']['P6ChangeRead']
export type P6Rule = components['schemas']['P6RuleRead']
export type P6RuleCreate = components['schemas']['P6RuleCreate']
export type RuleTestResult = components['schemas']['RuleTestResult']
export type Unmatched = components['schemas']['UnmatchedActivity']
export type ProgressRow = components['schemas']['ProgressRow']
export type P6Export = components['schemas']['P6ExportRead']
export type P6Settings = components['schemas']['P6Settings']

const keys = {
  all: (p: number) => ['p6', p] as const,
  imports: (p: number) => ['p6', p, 'imports'] as const,
  changes: (p: number, id: number) => ['p6', p, 'changes', id] as const,
  rules: (p: number) => ['p6', p, 'rules'] as const,
  unmatched: (p: number) => ['p6', p, 'unmatched'] as const,
  progress: (p: number) => ['p6', p, 'progress'] as const,
  exports: (p: number) => ['p6', p, 'exports'] as const,
  settings: (p: number) => ['p6', p, 'settings'] as const,
}

function useRefresh(projectId: number) {
  const qc = useQueryClient()
  return () => void qc.invalidateQueries({ queryKey: keys.all(projectId) })
}

export function useImports(projectId: number) {
  return useQuery({
    queryKey: keys.imports(projectId),
    queryFn: async () =>
      (
        await unwrap(
          api.GET('/api/v1/schedule/{project_id}/p6/imports/', {
            params: {
              path: { project_id: projectId },
              query: { items_per_page: 20 },
            },
          })
        )
      ).data,
  })
}

export function useChanges(projectId: number, importId: number | undefined) {
  return useQuery({
    queryKey: keys.changes(projectId, importId ?? 0),
    queryFn: async () =>
      (
        await allPages((page) =>
          unwrap(
            api.GET(
              '/api/v1/schedule/{project_id}/p6/imports/{import_id}/changes/',
              {
                params: {
                  path: { project_id: projectId, import_id: importId! },
                  query: { page, items_per_page: 100 },
                },
              }
            )
          )
        )
      ).data,
    enabled: !!importId,
  })
}

export function useUpload(projectId: number) {
  const refresh = useRefresh(projectId)
  return useMutation({
    mutationFn: async ({
      file,
      createMissing,
      createUnder,
    }: {
      file: File
      createMissing: boolean
      createUnder: number | null
    }): Promise<P6Import> => {
      const form = new FormData()
      form.append('file', file)
      form.append('create_missing', String(createMissing))
      if (createUnder) form.append('create_under_node_id', String(createUnder))
      const response = await fetch(`/api/v1/schedule/${projectId}/p6/imports`, {
        method: 'POST',
        credentials: 'include',
        headers: csrfHeaders(),
        body: form,
      })
      const body = await response.json().catch(() => ({}))
      if (!response.ok) throw new ApiError(response.status, body.detail)
      return body as P6Import
    },
    onSuccess: refresh,
    onError: handleServerError,
  })
}

export function useImportActions(projectId: number) {
  const refresh = useRefresh(projectId)
  const exclude = useMutation({
    mutationFn: ({
      importId,
      changeId,
      excluded,
    }: {
      importId: number
      changeId: number
      excluded: boolean
    }) =>
      unwrap(
        api.PATCH(
          '/api/v1/schedule/{project_id}/p6/imports/{import_id}/changes/{change_id}',
          {
            params: {
              path: {
                project_id: projectId,
                import_id: importId,
                change_id: changeId,
              },
            },
            body: { excluded },
          }
        )
      ),
    onSuccess: refresh,
    onError: handleServerError,
  })
  const commit = useMutation({
    mutationFn: (importId: number) =>
      unwrap(
        api.POST(
          '/api/v1/schedule/{project_id}/p6/imports/{import_id}/commit',
          { params: { path: { project_id: projectId, import_id: importId } } }
        )
      ),
    onSuccess: refresh,
    onError: handleServerError,
  })
  const discard = useMutation({
    mutationFn: (importId: number) =>
      unwrap(
        api.POST(
          '/api/v1/schedule/{project_id}/p6/imports/{import_id}/discard',
          { params: { path: { project_id: projectId, import_id: importId } } }
        )
      ),
    onSuccess: refresh,
    onError: handleServerError,
  })
  return { exclude, commit, discard }
}

export function useUnmatched(projectId: number) {
  return useQuery({
    queryKey: keys.unmatched(projectId),
    queryFn: async () =>
      await allPages((page) =>
        unwrap(
          api.GET('/api/v1/schedule/{project_id}/p6/unmatched/', {
            params: {
              path: { project_id: projectId },
              query: { page, items_per_page: 100 },
            },
          })
        )
      ),
  })
}

export function useLinkActions(projectId: number) {
  const refresh = useRefresh(projectId)
  const link = useMutation({
    mutationFn: ({
      activityId,
      nodeId,
      remember,
    }: {
      activityId: number
      nodeId: number
      remember: boolean
    }) =>
      unwrap(
        api.POST(
          '/api/v1/schedule/{project_id}/p6/activities/{activity_id}/links',
          {
            params: {
              path: { project_id: projectId, activity_id: activityId },
            },
            body: { node_id: nodeId, remember },
          }
        )
      ),
    onSuccess: refresh,
    onError: handleServerError,
  })
  const confirm = useMutation({
    mutationFn: (linkId: number) =>
      unwrap(
        api.POST('/api/v1/schedule/{project_id}/p6/links/{link_id}/confirm', {
          params: { path: { project_id: projectId, link_id: linkId } },
        })
      ),
    onSuccess: refresh,
    onError: handleServerError,
  })
  return { link, confirm }
}

export function useRules(projectId: number) {
  return useQuery({
    queryKey: keys.rules(projectId),
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/schedule/{project_id}/p6/rules', {
          params: { path: { project_id: projectId } },
        })
      ),
  })
}

export function useRuleActions(projectId: number) {
  const refresh = useRefresh(projectId)
  const create = useMutation({
    mutationFn: (body: P6RuleCreate) =>
      unwrap(
        api.POST('/api/v1/schedule/{project_id}/p6/rules', {
          params: { path: { project_id: projectId } },
          body,
        })
      ),
    onSuccess: refresh,
    onError: handleServerError,
  })
  const update = useMutation({
    mutationFn: ({
      id,
      body,
    }: {
      id: number
      body: Partial<Omit<P6RuleCreate, 'kind'>>
    }) =>
      unwrap(
        api.PATCH('/api/v1/schedule/{project_id}/p6/rules/{rule_id}', {
          params: { path: { project_id: projectId, rule_id: id } },
          body: body as never,
        })
      ),
    onSuccess: refresh,
    onError: handleServerError,
  })
  const remove = useMutation({
    mutationFn: (id: number) =>
      unwrap(
        api.DELETE('/api/v1/schedule/{project_id}/p6/rules/{rule_id}', {
          params: { path: { project_id: projectId, rule_id: id } },
        })
      ),
    onSuccess: refresh,
    onError: handleServerError,
  })
  const test = useMutation({
    mutationFn: (body: {
      samples: { name: string; code?: string | null }[]
      pattern?: string | null
      source?: 'name' | 'code' | 'wbs'
    }) =>
      unwrap(
        api.POST('/api/v1/schedule/{project_id}/p6/rules/test', {
          params: { path: { project_id: projectId } },
          body: body as never,
        })
      ),
    onError: handleServerError,
  })
  return { create, update, remove, test }
}

export function useP6Settings(projectId: number) {
  const refresh = useRefresh(projectId)
  const query = useQuery({
    queryKey: keys.settings(projectId),
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/schedule/{project_id}/p6/settings', {
          params: { path: { project_id: projectId } },
        })
      ),
  })
  const save = useMutation({
    mutationFn: (body: P6Settings) =>
      unwrap(
        api.PUT('/api/v1/schedule/{project_id}/p6/settings', {
          params: { path: { project_id: projectId } },
          body,
        })
      ),
    onSuccess: refresh,
    onError: handleServerError,
  })
  return { query, save }
}

export function useProgress(projectId: number) {
  return useQuery({
    queryKey: keys.progress(projectId),
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/schedule/{project_id}/p6/progress', {
          params: { path: { project_id: projectId } },
        })
      ),
  })
}

export function useExports(projectId: number) {
  return useQuery({
    queryKey: keys.exports(projectId),
    queryFn: async () =>
      (
        await unwrap(
          api.GET('/api/v1/schedule/{project_id}/p6/exports/', {
            params: {
              path: { project_id: projectId },
              query: { items_per_page: 50 },
            },
          })
        )
      ).data,
  })
}

export function useExportActions(projectId: number) {
  const refresh = useRefresh(projectId)
  const create = useMutation({
    mutationFn: (body: {
      format: 'xer' | 'p6_xml' | 'csv'
      only_changed: boolean
    }) =>
      unwrap(
        api.POST('/api/v1/schedule/{project_id}/p6/exports', {
          params: { path: { project_id: projectId } },
          body,
        })
      ),
    onSuccess: (exp) => {
      refresh()
      window.open(downloadUrl(projectId, exp.id), '_blank')
    },
    onError: handleServerError,
  })
  const verify = useMutation({
    mutationFn: (body: {
      node_id: number
      verified_qty: string
      inspection_id?: number | null
      note?: string | null
    }) =>
      unwrap(
        api.POST('/api/v1/schedule/{project_id}/progress/verifications', {
          params: { path: { project_id: projectId } },
          body,
        })
      ),
    onSuccess: refresh,
    onError: handleServerError,
  })
  return { create, verify }
}

export const downloadUrl = (projectId: number, exportId: number) =>
  `/api/v1/schedule/${projectId}/p6/exports/${exportId}/download`
