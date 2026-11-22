import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, unwrap } from '@/api/client'

export const notificationKeys = { all: ['notifications'] as const }

export function useUnreadCount() {
  return useQuery({
    queryKey: [...notificationKeys.all, 'unread'],
    queryFn: () => unwrap(api.GET('/api/v1/notifications/unread-count')),
    refetchInterval: 30_000,
  })
}

export function useNotifications(unreadOnly = false) {
  return useQuery({
    queryKey: [...notificationKeys.all, 'list', unreadOnly],
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/notifications/', {
          params: { query: { unread_only: unreadOnly, items_per_page: 50 } },
        })
      ),
  })
}

export function useMarkRead() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, read }: { id: number; read: boolean }) =>
      unwrap(
        api.PATCH('/api/v1/notifications/{notification_id}/read', {
          params: { path: { notification_id: id }, query: { read } },
        })
      ),
    onSuccess: () =>
      void queryClient.invalidateQueries({ queryKey: notificationKeys.all }),
  })
}

export function useReadAll() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => unwrap(api.POST('/api/v1/notifications/read-all')),
    onSuccess: () =>
      void queryClient.invalidateQueries({ queryKey: notificationKeys.all }),
  })
}
