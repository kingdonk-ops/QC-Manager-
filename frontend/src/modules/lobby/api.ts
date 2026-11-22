import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, unwrap } from '@/api/client'
import type { components } from '@/api/schema'
import { handleServerError } from '@/lib/handle-server-error'

type S = components['schemas']
export type LobbyProject = S['LobbyProject']
export type AccessRequest = S['AccessRequestRead']
export type Invite = S['InviteRead']

function useRefresh() {
  const qc = useQueryClient()
  return () => {
    void qc.invalidateQueries({ queryKey: ['lobby'] })
    void qc.invalidateQueries({ queryKey: ['projects'] })
  }
}

export function useLobbyProjects() {
  return useQuery({
    queryKey: ['lobby', 'projects'],
    queryFn: async () =>
      (await unwrap(api.GET('/api/v1/lobby/projects/'))).data,
  })
}

export function useMyRequests() {
  return useQuery({
    queryKey: ['lobby', 'mine'],
    queryFn: () => unwrap(api.GET('/api/v1/lobby/requests/mine')),
  })
}

export function useClaim() {
  const refresh = useRefresh()
  return useMutation({
    mutationFn: () => unwrap(api.POST('/api/v1/lobby/claim')),
    onSuccess: (joined) => joined.length && refresh(),
  })
}

export function useFileRequest() {
  const refresh = useRefresh()
  return useMutation({
    mutationFn: (body: {
      project_id?: number
      code?: string
      message?: string
    }) => unwrap(api.POST('/api/v1/lobby/requests', { body })),
    onSuccess: refresh,
    onError: handleServerError,
  })
}

export function useWithdraw() {
  const refresh = useRefresh()
  return useMutation({
    mutationFn: (id: number) =>
      unwrap(
        api.POST('/api/v1/lobby/requests/{request_id}/withdraw', {
          params: { path: { request_id: id } },
        })
      ),
    onSuccess: refresh,
    onError: handleServerError,
  })
}

export function useJoin() {
  const refresh = useRefresh()
  return useMutation({
    mutationFn: (inviteId: number) =>
      unwrap(
        api.POST('/api/v1/lobby/invites/{invite_id}/join', {
          params: { path: { invite_id: inviteId } },
        })
      ),
    onSuccess: refresh,
    onError: handleServerError,
  })
}

export async function lookup(code: string) {
  return unwrap(
    api.GET('/api/v1/lobby/lookup', { params: { query: { code } } })
  )
}

// --- admin ---------------------------------------------------------------------------------------

export function useRequestQueue(status: string) {
  return useQuery({
    queryKey: ['lobby', 'queue', status],
    queryFn: async () =>
      (
        await unwrap(
          api.GET('/api/v1/lobby/requests/', {
            params: { query: { status: status as never } },
          })
        )
      ).data,
  })
}

export function useDecide() {
  const refresh = useRefresh()
  return useMutation({
    mutationFn: ({
      id,
      approve,
      reason,
      grant,
    }: {
      id: number
      approve: boolean
      reason?: string
      grant?: 'member' | 'client_team'
    }) =>
      approve
        ? unwrap(
            api.POST('/api/v1/lobby/requests/{request_id}/approve', {
              params: { path: { request_id: id } },
              body: { grant: grant ?? null },
            })
          )
        : unwrap(
            api.POST('/api/v1/lobby/requests/{request_id}/reject', {
              params: { path: { request_id: id } },
              body: { reason: reason || null },
            })
          ),
    onSuccess: refresh,
    onError: handleServerError,
  })
}

const project = (id: number) => ({ params: { path: { project_id: id } } })

export function useListing(projectId: number) {
  return useQuery({
    queryKey: ['lobby', 'listing', projectId],
    queryFn: () =>
      unwrap(
        api.GET(
          '/api/v1/lobby/projects/{project_id}/listing',
          project(projectId)
        )
      ),
  })
}

export function useSetListing(projectId: number) {
  const refresh = useRefresh()
  return useMutation({
    mutationFn: (visible: boolean) =>
      unwrap(
        api.PUT('/api/v1/lobby/projects/{project_id}/listing', {
          ...project(projectId),
          body: { visible },
        })
      ),
    onSuccess: refresh,
    onError: handleServerError,
  })
}

export function useMembers(projectId: number) {
  return useQuery({
    queryKey: ['lobby', 'members', projectId],
    queryFn: () =>
      unwrap(
        api.GET(
          '/api/v1/lobby/projects/{project_id}/members',
          project(projectId)
        )
      ),
  })
}

export function useInvites(projectId: number) {
  return useQuery({
    queryKey: ['lobby', 'invites', projectId],
    queryFn: () =>
      unwrap(
        api.GET(
          '/api/v1/lobby/projects/{project_id}/invites',
          project(projectId)
        )
      ),
  })
}

export function useInvite(projectId: number) {
  const refresh = useRefresh()
  return useMutation({
    mutationFn: (body: { email: string; name?: string }) =>
      unwrap(
        api.POST('/api/v1/lobby/projects/{project_id}/invites', {
          ...project(projectId),
          body: { email: body.email, name: body.name || null },
        })
      ),
    onSuccess: refresh,
    onError: handleServerError,
  })
}

export function useInviteAction() {
  const refresh = useRefresh()
  return useMutation({
    mutationFn: ({
      id,
      action,
    }: {
      id: number
      action: 'revoke' | 'resend'
    }) =>
      action === 'revoke'
        ? unwrap(
            api.POST('/api/v1/lobby/invites/{invite_id}/revoke', {
              params: { path: { invite_id: id } },
            })
          )
        : unwrap(
            api.POST('/api/v1/lobby/invites/{invite_id}/resend', {
              params: { path: { invite_id: id } },
            })
          ),
    onSuccess: refresh,
    onError: handleServerError,
  })
}

// --- invite links --------------------------------------------------------------------------------

export function previewInvite(token: string) {
  return unwrap(api.POST('/api/v1/lobby/invites/preview', { body: { token } }))
}

export function acceptInvite(token: string) {
  return unwrap(api.POST('/api/v1/lobby/invites/accept', { body: { token } }))
}

/** The token travels in the URL fragment (never sent to a server), and is kept across the sign-in. */
const PENDING = 'qc.pending-invite'

export function inviteToken(): string | null {
  const fromHash = window.location.hash.replace(/^#/, '')
  if (/^[A-Za-z0-9_-]{20,200}$/.test(fromHash)) {
    try {
      sessionStorage.setItem(PENDING, fromHash)
    } catch {
      // storage unavailable: the hash still works on this load
    }
    return fromHash
  }
  try {
    return sessionStorage.getItem(PENDING)
  } catch {
    return null
  }
}

export function forgetInvite() {
  try {
    sessionStorage.removeItem(PENDING)
  } catch {
    // nothing stored
  }
}
