import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, unwrap } from '@/api/client'
import type { components } from '@/api/schema'
import { handleServerError } from '@/lib/handle-server-error'

export type Task = components['schemas']['TaskRead']
export type Board = components['schemas']['Board']
export type Assignee = components['schemas']['Assignee']
export type TaskCreate = components['schemas']['TaskCreate']
export type TaskUpdate = components['schemas']['TaskUpdate']
export type TaskStatus = components['schemas']['TaskStatus']

export const taskKeys = {
  board: (projectId: number) => ['tasks', 'board', projectId] as const,
  one: (id: number) => ['tasks', 'one', id] as const,
  assignees: ['tasks', 'assignees'] as const,
}

export function useBoard(projectId: number) {
  return useQuery({
    queryKey: taskKeys.board(projectId),
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/tasks/board/{project_id}', {
          params: { path: { project_id: projectId } },
        })
      ),
  })
}

export function useTask(id: number | null) {
  return useQuery({
    queryKey: taskKeys.one(id ?? 0),
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/tasks/{task_id}', {
          params: { path: { task_id: id! } },
        })
      ),
    enabled: id !== null && id > 0,
  })
}

/** Accounts work can be assigned to: used by Tasks and Meetings. */
export function useAssignees(enabled = true) {
  return useQuery({
    queryKey: taskKeys.assignees,
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/tasks/assignees', {
          params: { query: { limit: 500 } },
        })
      ),
    staleTime: 5 * 60_000,
    enabled,
  })
}

function useRefresh(projectId: number) {
  const queryClient = useQueryClient()
  return () => {
    void queryClient.invalidateQueries({ queryKey: taskKeys.board(projectId) })
    void queryClient.invalidateQueries({ queryKey: ['tasks', 'one'] })
  }
}

export function useCreateTask(projectId: number) {
  const refresh = useRefresh(projectId)
  return useMutation({
    mutationFn: (body: TaskCreate) =>
      unwrap(api.POST('/api/v1/tasks/', { body })),
    onSuccess: refresh,
    onError: handleServerError,
  })
}

export function useUpdateTask(projectId: number) {
  const refresh = useRefresh(projectId)
  return useMutation({
    mutationFn: ({ id, body }: { id: number; body: TaskUpdate }) =>
      unwrap(
        api.PATCH('/api/v1/tasks/{task_id}', {
          params: { path: { task_id: id } },
          body,
        })
      ),
    onSuccess: refresh,
    onError: (error) => {
      handleServerError(error)
      refresh()
    },
  })
}

export function useDeleteTask(projectId: number) {
  const refresh = useRefresh(projectId)
  return useMutation({
    mutationFn: (id: number) =>
      unwrap(
        api.DELETE('/api/v1/tasks/{task_id}', {
          params: { path: { task_id: id } },
        })
      ),
    onSuccess: refresh,
    onError: handleServerError,
  })
}

export type MoveArgs = {
  id: number
  status: TaskStatus
  before_id?: number | null
  override_wip?: boolean
}

/** Moves a card. Errors are left to the caller, which offers "Move anyway" on a WIP refusal. */
export function useMoveTask(projectId: number) {
  const refresh = useRefresh(projectId)
  return useMutation({
    mutationFn: ({ id, ...body }: MoveArgs) =>
      unwrap(
        api.POST('/api/v1/tasks/{task_id}/move', {
          params: { path: { task_id: id } },
          body: {
            status: body.status,
            before_id: body.before_id ?? null,
            override_wip: body.override_wip ?? false,
          },
        })
      ),
    onSettled: refresh,
  })
}

export function useSetWipLimits(projectId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (limits: Partial<Record<TaskStatus, number>>) =>
      unwrap(
        api.PUT('/api/v1/tasks/board/{project_id}/limits', {
          params: { path: { project_id: projectId } },
          body: { wip_limits: limits },
        })
      ),
    onSuccess: (board) =>
      queryClient.setQueryData(taskKeys.board(projectId), board),
    onError: handleServerError,
  })
}
