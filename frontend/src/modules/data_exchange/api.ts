import { useQuery } from '@tanstack/react-query'
import { ApiError, api, csrfHeaders, unwrap } from '@/api/client'
import type { components } from '@/api/schema'

export type DatasetInfo = components['schemas']['DatasetInfo']
export type ImporterInfo = components['schemas']['ImporterInfo']
export type ImportReport = components['schemas']['DataImportReport']
export type Preview = {
  columns: string[]
  rows: number
  sample: Record<string, unknown>[]
  mapping: Record<string, string>
}

export function useExportDatasets(projectId?: number) {
  return useQuery({
    queryKey: ['data', 'datasets', projectId ?? null],
    queryFn: async () =>
      (
        await unwrap(
          api.GET('/api/v1/data/datasets/', {
            params: { query: { project_id: projectId, items_per_page: 100 } },
          })
        )
      ).data,
  })
}

export function useImporters(projectId?: number, enabled = true) {
  return useQuery({
    queryKey: ['data', 'importers', projectId ?? null],
    enabled,
    queryFn: async () =>
      (
        await unwrap(
          api.GET('/api/v1/data/importers/', {
            params: { query: { project_id: projectId, items_per_page: 100 } },
          })
        )
      ).data,
  })
}

async function failure(response: Response): Promise<never> {
  let detail: unknown = response.statusText
  try {
    detail = (await response.json()).detail
  } catch {
    /* not JSON */
  }
  throw new ApiError(response.status, detail)
}

/** Multipart POST to the import endpoints (the typed client doesn't do files). */
export async function postForm<T>(url: string, form: FormData): Promise<T> {
  const response = await fetch(url, {
    method: 'POST',
    credentials: 'include',
    headers: csrfHeaders(),
    body: form,
  })
  if (!response.ok) return failure(response)
  return (await response.json()) as T
}

/** Fetches an export and saves it under the server's file name. */
export async function saveExport(url: string) {
  const response = await fetch(url, { credentials: 'include' })
  if (!response.ok) return failure(response)
  const name =
    /filename="([^"]+)"/.exec(
      response.headers.get('content-disposition') ?? ''
    )?.[1] ?? 'export'
  const link = document.createElement('a')
  link.href = URL.createObjectURL(await response.blob())
  link.download = name
  document.body.appendChild(link)
  link.click()
  link.remove()
  setTimeout(() => URL.revokeObjectURL(link.href), 1000)
}

export function exportUrl(
  dataset: string,
  {
    projectId,
    format,
    columns,
    filters,
  }: {
    projectId?: number
    format: 'xlsx' | 'csv' | 'pdf'
    columns: string[]
    filters: Record<string, unknown>
  }
) {
  const query = new URLSearchParams({ format })
  if (projectId) query.set('project_id', String(projectId))
  if (columns.length) query.set('columns', columns.join(','))
  if (Object.keys(filters).length) query.set('filters', JSON.stringify(filters))
  return `/api/v1/data/export/${encodeURIComponent(dataset)}?${query}`
}
