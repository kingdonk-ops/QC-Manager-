import { useQuery } from '@tanstack/react-query'
import { api, unwrap } from '@/api/client'
import type { components } from '@/api/schema'

export type Markup = components['schemas']['MarkupRead']
export type MarkupSet = components['schemas']['MarkupSetRead']
export type Calibration = components['schemas']['MarkupCalibrationRead']
export type Stamp = components['schemas']['MarkupStampRead']
export type MarkupCreate = components['schemas']['MarkupCreate']
export type MarkupType = MarkupCreate['type']
export type Style = components['schemas']['MarkupStyle']

export const keys = {
  markups: (fileId: number) => ['markups', fileId, 'items'] as const,
  sets: (fileId: number) => ['markups', fileId, 'sets'] as const,
  calibrations: (fileId: number) =>
    ['markups', fileId, 'calibrations'] as const,
  stamps: (projectId: number) => ['markups', 'stamps', projectId] as const,
}

/** Every markup on a drawing, following the pages of the listing. */
async function allMarkups(fileId: number) {
  const out: Markup[] = []
  for (let page = 1; ; page++) {
    const res = await unwrap(
      api.GET('/api/v1/markups/', {
        params: { query: { file_id: fileId, page, items_per_page: 100 } },
      })
    )
    out.push(...res.data)
    if (!res.has_more) return out
  }
}

export function useMarkups(fileId: number) {
  return useQuery({
    queryKey: keys.markups(fileId),
    queryFn: () => allMarkups(fileId),
  })
}

export function useSets(fileId: number) {
  return useQuery({
    queryKey: keys.sets(fileId),
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/markups/sets/', {
          params: { query: { file_id: fileId, items_per_page: 100 } },
        })
      ).then((r) => r.data),
  })
}

export function useCalibrations(fileId: number) {
  return useQuery({
    queryKey: keys.calibrations(fileId),
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/markups/calibrations/', {
          params: { query: { file_id: fileId, items_per_page: 100 } },
        })
      ).then((r) => r.data),
  })
}

export function useStamps(projectId: number | null | undefined) {
  return useQuery({
    queryKey: keys.stamps(projectId ?? 0),
    enabled: !!projectId,
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/markups/stamps/', {
          params: { query: { project_id: projectId!, items_per_page: 100 } },
        })
      ).then((r) => r.data),
  })
}

export function useDrawing(fileId: number) {
  return useQuery({
    queryKey: ['files', 'one', fileId],
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/files/{file_id}', {
          params: { path: { file_id: fileId } },
        })
      ),
  })
}

export const createMarkup = (body: MarkupCreate) =>
  unwrap(api.POST('/api/v1/markups/', { body }))

export const updateMarkup = (
  id: number,
  body: components['schemas']['MarkupUpdate']
) =>
  unwrap(
    api.PATCH('/api/v1/markups/{markup_id}', {
      params: { path: { markup_id: id } },
      body,
    })
  )

export const deleteMarkup = (id: number) =>
  unwrap(
    api.DELETE('/api/v1/markups/{markup_id}', {
      params: { path: { markup_id: id } },
    })
  )

export const flattenedUrl = (fileId: number, setIds?: number[]) => {
  const query = (setIds ?? []).map((id) => `set_ids=${id}`).join('&')
  return `/api/v1/markups/${fileId}/flattened.pdf${query ? `?${query}` : ''}`
}
