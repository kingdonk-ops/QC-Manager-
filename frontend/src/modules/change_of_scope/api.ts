import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, unwrap } from '@/api/client'
import type { components } from '@/api/schema'
import { handleServerError } from '@/lib/handle-server-error'

export type Card = components['schemas']['CardRead']
export type CardCreate = components['schemas']['CardCreate']
export type CardUpdate = components['schemas']['CardUpdate']
export type CardLine = components['schemas']['CardLine']
export type CardSummary = components['schemas']['CardSummary']

export const CHANGE_TYPES = [
  'scope_increase',
  'descope',
  'scope_change',
  'already_done',
  'not_found',
  'needs_assessment',
  'client_to_confirm',
] as const
export const SOURCES = [
  'site_instruction',
  'client_direction',
  'field_finding',
  'other',
] as const
export const FILTERS = [
  'waiting',
  'draft',
  'submitted',
  'acknowledged',
  'approved',
  'rejected',
  'converted',
  'expired',
  'withdrawn',
] as const

/** Moves offered from each status, with the permission each needs. */
export const MOVES: Record<string, { to: string; permission: string }[]> = {
  draft: [
    { to: 'submitted', permission: 'change_of_scope.submit' },
    { to: 'withdrawn', permission: 'change_of_scope.submit' },
  ],
  submitted: [
    { to: 'acknowledged', permission: 'change_of_scope.respond' },
    { to: 'approved', permission: 'change_of_scope.approve' },
    { to: 'rejected', permission: 'change_of_scope.approve' },
    { to: 'draft', permission: 'change_of_scope.submit' },
    { to: 'withdrawn', permission: 'change_of_scope.submit' },
  ],
  acknowledged: [
    { to: 'approved', permission: 'change_of_scope.approve' },
    { to: 'rejected', permission: 'change_of_scope.approve' },
    { to: 'withdrawn', permission: 'change_of_scope.submit' },
  ],
  rejected: [{ to: 'draft', permission: 'change_of_scope.submit' }],
  expired: [
    { to: 'submitted', permission: 'change_of_scope.submit' },
    { to: 'withdrawn', permission: 'change_of_scope.submit' },
  ],
  withdrawn: [{ to: 'draft', permission: 'change_of_scope.submit' }],
  approved: [],
  converted: [],
}

/** Estimate of a line: quantity × rate, to the cent. */
export function lineAmount(line: { quantity?: unknown; rate?: unknown }) {
  return (
    Math.round(Number(line.quantity || 0) * Number(line.rate || 0) * 100) / 100
  )
}

const keys = {
  all: (p: number) => ['change_of_scope', p] as const,
  list: (p: number, status: string, search: string) =>
    ['change_of_scope', p, 'list', status, search] as const,
  summary: (p: number) => ['change_of_scope', p, 'summary'] as const,
  one: (p: number, id: number) => ['change_of_scope', p, 'one', id] as const,
  history: (p: number, id: number) =>
    ['change_of_scope', p, 'history', id] as const,
}

function useRefresh(projectId: number) {
  const qc = useQueryClient()
  return () => void qc.invalidateQueries({ queryKey: keys.all(projectId) })
}

export function useCards(projectId: number, status: string, search: string) {
  return useQuery({
    queryKey: keys.list(projectId, status, search),
    queryFn: async () =>
      (
        await unwrap(
          api.GET('/api/v1/change-of-scope/cards/', {
            params: {
              query: {
                project_id: projectId,
                status: (status || undefined) as never,
                search: search || undefined,
                items_per_page: 200,
              },
            },
          })
        )
      ).data,
  })
}

export function useSummary(projectId: number) {
  return useQuery({
    queryKey: keys.summary(projectId),
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/change-of-scope/summary', {
          params: { query: { project_id: projectId } },
        })
      ),
  })
}

export function useCard(projectId: number, id: number | undefined) {
  return useQuery({
    queryKey: keys.one(projectId, id ?? 0),
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/change-of-scope/cards/{card_id}', {
          params: { path: { card_id: id! } },
        })
      ),
    enabled: !!id,
  })
}

export function useHistory(projectId: number, id: number) {
  return useQuery({
    queryKey: keys.history(projectId, id),
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/change-of-scope/cards/{card_id}/history', {
          params: { path: { card_id: id } },
        })
      ),
  })
}

export function useCardActions(projectId: number) {
  const refresh = useRefresh(projectId)
  const create = useMutation({
    mutationFn: (body: Omit<CardCreate, 'project_id'>) =>
      unwrap(
        api.POST('/api/v1/change-of-scope/cards/', {
          body: { ...body, project_id: projectId },
        })
      ),
    onSuccess: refresh,
    onError: handleServerError,
  })
  const update = useMutation({
    mutationFn: ({ id, body }: { id: number; body: CardUpdate }) =>
      unwrap(
        api.PATCH('/api/v1/change-of-scope/cards/{card_id}', {
          params: { path: { card_id: id } },
          body,
        })
      ),
    onSuccess: refresh,
    onError: handleServerError,
  })
  const move = useMutation({
    mutationFn: ({
      id,
      status,
      note,
      approvedAmount,
    }: {
      id: number
      status: string
      note?: string
      approvedAmount?: string
    }) =>
      unwrap(
        api.PATCH('/api/v1/change-of-scope/cards/{card_id}/status', {
          params: { path: { card_id: id } },
          body: {
            status: status as never,
            note: note || null,
            approved_amount: approvedAmount || null,
          },
        })
      ),
    onSuccess: refresh,
    onError: handleServerError,
  })
  const convert = useMutation({
    mutationFn: (id: number) =>
      unwrap(
        api.POST('/api/v1/change-of-scope/cards/{card_id}/convert', {
          params: { path: { card_id: id } },
        })
      ),
    onSuccess: refresh,
    onError: handleServerError,
  })
  const remove = useMutation({
    mutationFn: (id: number) =>
      unwrap(
        api.DELETE('/api/v1/change-of-scope/cards/{card_id}', {
          params: { path: { card_id: id } },
        })
      ),
    onSuccess: refresh,
    onError: handleServerError,
  })
  return { create, update, move, convert, remove }
}

export const exportUrl = (projectId: number) =>
  `/api/v1/change-of-scope/cards/export?project_id=${projectId}&format=xlsx`
