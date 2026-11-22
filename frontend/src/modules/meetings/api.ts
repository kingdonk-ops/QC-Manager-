import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, unwrap } from '@/api/client'
import type { components } from '@/api/schema'
import { handleServerError } from '@/lib/handle-server-error'

type S = components['schemas']
export type Meeting = S['MeetingRead']
export type MeetingDetail = S['MeetingDetail']
export type MeetingCreate = S['MeetingCreate']
export type MeetingUpdate = S['MeetingUpdate']
export type Series = S['SeriesRead']
export type SeriesIn = S['SeriesIn']
export type AgendaItem = S['AgendaItemRead']
export type AgendaItemIn = S['AgendaItemIn']
export type AgendaItemUpdate = S['AgendaItemUpdate']
export type Attendee = S['AttendeeRead']
export type Action = S['ActionRead']
export type ActionIn = S['ActionIn']
export type ActionUpdate = S['ActionUpdate']
export type Previous = S['PreviousMeeting']
export type MeetingStatus = S['MeetingStatus']
export type Person = { user_id?: number | null; contact_id?: number | null }

export const meetingKeys = {
  all: ['meetings'] as const,
  list: (projectId: number) => ['meetings', 'list', projectId] as const,
  one: (id: number) => ['meetings', 'one', id] as const,
  previous: (id: number) => ['meetings', 'previous', id] as const,
  history: (id: number) => ['meetings', 'history', id] as const,
  series: (projectId: number) => ['meetings', 'series', projectId] as const,
}

const at = (meeting_id: number) => ({ params: { path: { meeting_id } } })

export function useMeetings(projectId: number) {
  return useQuery({
    queryKey: meetingKeys.list(projectId),
    queryFn: async () =>
      (
        await unwrap(
          api.GET('/api/v1/meetings/', {
            params: { query: { project_id: projectId, items_per_page: 100 } },
          })
        )
      ).data,
  })
}

export function useMeeting(id: number | null) {
  return useQuery({
    queryKey: meetingKeys.one(id ?? 0),
    queryFn: () => unwrap(api.GET('/api/v1/meetings/{meeting_id}', at(id!))),
    enabled: Boolean(id),
  })
}

export function usePrevious(id: number, enabled: boolean) {
  return useQuery({
    queryKey: meetingKeys.previous(id),
    queryFn: () =>
      unwrap(api.GET('/api/v1/meetings/{meeting_id}/previous', at(id))),
    enabled,
  })
}

export function useHistory(id: number) {
  return useQuery({
    queryKey: meetingKeys.history(id),
    queryFn: () =>
      unwrap(api.GET('/api/v1/meetings/{meeting_id}/history', at(id))),
  })
}

export function useSeries(projectId: number) {
  return useQuery({
    queryKey: meetingKeys.series(projectId),
    queryFn: async () =>
      (
        await unwrap(
          api.GET('/api/v1/meetings/series/', {
            params: {
              query: {
                project_id: projectId,
                items_per_page: 100,
                include_inactive: true,
              },
            },
          })
        )
      ).data,
  })
}

function useRefresh() {
  const queryClient = useQueryClient()
  return () => {
    void queryClient.invalidateQueries({ queryKey: meetingKeys.all })
    void queryClient.invalidateQueries({ queryKey: ['tasks'] })
  }
}

/** A mutation that refreshes every meetings query afterwards and toasts errors. */
function useAct<A, R>(fn: (args: A) => Promise<R>) {
  const refresh = useRefresh()
  return useMutation({
    mutationFn: fn,
    onSuccess: refresh,
    onError: (error) => {
      handleServerError(error)
      refresh()
    },
  })
}

export function useCreateMeeting() {
  return useAct((body: MeetingCreate) =>
    unwrap(api.POST('/api/v1/meetings/', { body }))
  )
}

export function useUpdateMeeting(id: number) {
  return useAct((body: MeetingUpdate) =>
    unwrap(api.PATCH('/api/v1/meetings/{meeting_id}', { ...at(id), body }))
  )
}

export function useDeleteMeeting() {
  return useAct((id: number) =>
    unwrap(api.DELETE('/api/v1/meetings/{meeting_id}', at(id)))
  )
}

export function useSetStatus(id: number) {
  return useAct((status: Exclude<MeetingStatus, 'minutes_issued'>) =>
    unwrap(
      api.POST('/api/v1/meetings/{meeting_id}/status', {
        ...at(id),
        body: { status },
      })
    )
  )
}

export function useIssueMinutes(id: number) {
  return useAct(() =>
    unwrap(api.POST('/api/v1/meetings/{meeting_id}/issue', at(id)))
  )
}

export function useAgenda(id: number) {
  const add = useAct((body: AgendaItemIn) =>
    unwrap(
      api.POST('/api/v1/meetings/{meeting_id}/agenda', { ...at(id), body })
    )
  )
  const update = useAct(
    ({ itemId, body }: { itemId: number; body: AgendaItemUpdate }) =>
      unwrap(
        api.PATCH('/api/v1/meetings/{meeting_id}/agenda/{item_id}', {
          params: { path: { meeting_id: id, item_id: itemId } },
          body,
        })
      )
  )
  const remove = useAct((itemId: number) =>
    unwrap(
      api.DELETE('/api/v1/meetings/{meeting_id}/agenda/{item_id}', {
        params: { path: { meeting_id: id, item_id: itemId } },
      })
    )
  )
  const reorder = useAct((ids: number[]) =>
    unwrap(
      api.PUT('/api/v1/meetings/{meeting_id}/agenda/order', {
        ...at(id),
        body: { ids },
      })
    )
  )
  return { add, update, remove, reorder }
}

export function useAttendees(id: number) {
  const add = useAct((person: Person) =>
    unwrap(
      api.POST('/api/v1/meetings/{meeting_id}/attendees', {
        ...at(id),
        body: { ...person, invited: true, attended: false },
      })
    )
  )
  const update = useAct(
    ({ attendeeId, attended }: { attendeeId: number; attended: boolean }) =>
      unwrap(
        api.PATCH('/api/v1/meetings/{meeting_id}/attendees/{attendee_id}', {
          params: { path: { meeting_id: id, attendee_id: attendeeId } },
          body: { attended },
        })
      )
  )
  const remove = useAct((attendeeId: number) =>
    unwrap(
      api.DELETE('/api/v1/meetings/{meeting_id}/attendees/{attendee_id}', {
        params: { path: { meeting_id: id, attendee_id: attendeeId } },
      })
    )
  )
  return { add, update, remove }
}

export function useActions(id: number) {
  const add = useAct((body: ActionIn) =>
    unwrap(
      api.POST('/api/v1/meetings/{meeting_id}/actions', { ...at(id), body })
    )
  )
  const update = useAct(
    ({
      actionId,
      meetingId,
      body,
    }: {
      actionId: number
      meetingId?: number
      body: ActionUpdate
    }) =>
      unwrap(
        api.PATCH('/api/v1/meetings/{meeting_id}/actions/{action_id}', {
          params: {
            path: { meeting_id: meetingId ?? id, action_id: actionId },
          },
          body,
        })
      )
  )
  const remove = useAct((actionId: number) =>
    unwrap(
      api.DELETE('/api/v1/meetings/{meeting_id}/actions/{action_id}', {
        params: { path: { meeting_id: id, action_id: actionId } },
      })
    )
  )
  const toTask = useAct((actionId: number) =>
    unwrap(
      api.POST('/api/v1/meetings/{meeting_id}/actions/{action_id}/task', {
        params: { path: { meeting_id: id, action_id: actionId } },
      })
    )
  )
  return { add, update, remove, toTask }
}

export function useSaveSeries() {
  return useAct(({ id, body }: { id?: number; body: SeriesIn }) => {
    if (!id) return unwrap(api.POST('/api/v1/meetings/series/', { body }))
    const { project_id: _project, ...changes } = body
    return unwrap(
      api.PATCH('/api/v1/meetings/series/{series_id}', {
        params: { path: { series_id: id } },
        body: changes,
      })
    )
  })
}

export function useDeleteSeries() {
  return useAct((id: number) =>
    unwrap(
      api.DELETE('/api/v1/meetings/series/{series_id}', {
        params: { path: { series_id: id } },
      })
    )
  )
}

export const minutesPdfUrl = (id: number) =>
  `/api/v1/meetings/${id}/minutes.pdf`
