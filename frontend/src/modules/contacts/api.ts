import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query'
import { api, csrfHeaders, unwrap } from '@/api/client'
import type { components } from '@/api/schema'
import { handleServerError } from '@/lib/handle-server-error'

export type Contact = components['schemas']['ContactRead']
export type ContactIn = components['schemas']['ContactIn']
export type Company = components['schemas']['CompanyRead']
export type CompanyIn = components['schemas']['CompanyIn']
export type ImportReport = components['schemas']['ImportReport']

export const CONTACT_TYPES = [
  'client',
  'subcontractor',
  'supplier',
  'consultant',
  'architect',
  'engineer',
  'authority',
  'internal',
  'other',
] as const

export type ContactFilters = {
  search: string
  type: string
  company_id: number | null
  project_id: number | null
  tag: string
}

export const PAGE_SIZE = 100

export const contactKeys = {
  all: ['contacts'] as const,
  list: (f: ContactFilters, page: number) =>
    ['contacts', 'list', f, page] as const,
  companies: (search: string) => ['contacts', 'companies', search] as const,
  names: (ids: number[]) => ['contacts', 'names', ids] as const,
}

export function filterQuery(f: ContactFilters) {
  return {
    search: f.search || undefined,
    type: f.type === 'all' ? undefined : (f.type as ContactIn['type']),
    company_id: f.company_id ?? undefined,
    project_id: f.project_id ?? undefined,
    tag: f.tag || undefined,
  }
}

export function useContacts(f: ContactFilters, page = 1, enabled = true) {
  return useQuery({
    queryKey: contactKeys.list(f, page),
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/contacts/', {
          params: {
            query: { ...filterQuery(f), page, items_per_page: PAGE_SIZE },
          },
        })
      ),
    placeholderData: keepPreviousData,
    enabled,
  })
}

export function useCompanies(search = '') {
  return useQuery({
    queryKey: contactKeys.companies(search),
    queryFn: async () =>
      (
        await unwrap(
          api.GET('/api/v1/contacts/companies/', {
            params: {
              query: { search: search || undefined, items_per_page: 100 },
            },
          })
        )
      ).data,
  })
}

function useRefresh() {
  const queryClient = useQueryClient()
  return () => void queryClient.invalidateQueries({ queryKey: contactKeys.all })
}

export function useSaveContact() {
  const refresh = useRefresh()
  return useMutation({
    mutationFn: ({ id, body }: { id?: number; body: ContactIn }) =>
      id
        ? unwrap(
            api.PUT('/api/v1/contacts/{contact_id}', {
              params: { path: { contact_id: id } },
              body,
            })
          )
        : unwrap(api.POST('/api/v1/contacts/', { body })),
    onSuccess: refresh,
    onError: handleServerError,
  })
}

export function useDeleteContact() {
  const refresh = useRefresh()
  return useMutation({
    mutationFn: (id: number) =>
      unwrap(
        api.DELETE('/api/v1/contacts/{contact_id}', {
          params: { path: { contact_id: id } },
        })
      ),
    onSuccess: refresh,
    onError: handleServerError,
  })
}

export function useLinkProject() {
  const refresh = useRefresh()
  return useMutation({
    mutationFn: async (v: {
      contactId: number
      projectId: number
      role: string | null
      unlink?: boolean
    }) => {
      const params = {
        params: {
          path: { project_id: v.projectId, contact_id: v.contactId },
        },
      }
      if (v.unlink) {
        await unwrap(
          api.DELETE(
            '/api/v1/contacts/projects/{project_id}/{contact_id}',
            params
          )
        )
        return
      }
      await unwrap(
        api.PUT('/api/v1/contacts/projects/{project_id}/{contact_id}', {
          ...params,
          body: { role: v.role },
        })
      )
    },
    onSuccess: refresh,
    onError: handleServerError,
  })
}

export function useSaveCompany() {
  const refresh = useRefresh()
  return useMutation({
    mutationFn: ({ id, body }: { id?: number; body: CompanyIn }) =>
      id
        ? unwrap(
            api.PUT('/api/v1/contacts/companies/{company_id}', {
              params: { path: { company_id: id } },
              body,
            })
          )
        : unwrap(api.POST('/api/v1/contacts/companies/', { body })),
    onSuccess: refresh,
    onError: handleServerError,
  })
}

export function useDeleteCompany() {
  const refresh = useRefresh()
  return useMutation({
    mutationFn: (id: number) =>
      unwrap(
        api.DELETE('/api/v1/contacts/companies/{company_id}', {
          params: { path: { company_id: id } },
        })
      ),
    onSuccess: refresh,
    onError: handleServerError,
  })
}

/** Names for contact ids, for other modules' screens. */
export function useContactNames(ids: number[]) {
  const sorted = [...new Set(ids)].sort((a, b) => a - b)
  return useQuery({
    queryKey: contactKeys.names(sorted),
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/contacts/lookup/names', {
          params: { query: { ids: sorted } },
        })
      ),
    enabled: sorted.length > 0,
  })
}

async function postForm<T>(url: string, form: FormData): Promise<T> {
  const response = await fetch(url, {
    method: 'POST',
    credentials: 'include',
    headers: csrfHeaders(),
    body: form,
  })
  const body = await response.json().catch(() => ({}))
  if (!response.ok)
    throw new Error(
      typeof body.detail === 'string' ? body.detail : 'Import failed'
    )
  return body as T
}

export type ImportPreview = {
  columns: string[]
  fields: string[]
  mapping: Record<string, string>
  sample: Record<string, unknown>[]
  rows: number
}

export function previewImport(file: File) {
  const form = new FormData()
  form.set('file', file)
  return postForm<ImportPreview>('/api/v1/contacts/import/preview', form)
}

export type ImportOptions = {
  mapping: Record<string, string>
  on_duplicate: 'skip' | 'update'
  dry_run: boolean
  project_id: number | null
  project_role: string
}

export function runImport(file: File, o: ImportOptions) {
  const form = new FormData()
  form.set('file', file)
  form.set('mapping', JSON.stringify(o.mapping))
  form.set('on_duplicate', o.on_duplicate)
  form.set('dry_run', String(o.dry_run))
  if (o.project_id) {
    form.set('project_id', String(o.project_id))
    if (o.project_role) form.set('project_role', o.project_role)
  }
  return postForm<ImportReport>('/api/v1/contacts/import', form)
}

/** The export URL for the current filters; the browser downloads it with the session cookie. */
export function exportUrl(f: ContactFilters, format: 'xlsx' | 'csv') {
  const query = new URLSearchParams({ format })
  for (const [k, v] of Object.entries(filterQuery(f)))
    if (v !== undefined) query.set(k, String(v))
  return `/api/v1/contacts/export?${query.toString()}`
}

export const BANKING_FIELDS = [
  'bank_name',
  'account_name',
  'branch_code',
  'account_number',
  'swift',
  'iban',
] as const
