import { queryOptions, useQuery } from '@tanstack/react-query'
import { api, unwrap } from '@/api/client'

export type Whoami = {
  id: number
  name: string
  username: string
  email: string
  profile_image_url?: string | null
  is_superuser: boolean
  account_type: 'staff' | 'external'
  sign_in_method: 'entra' | 'password'
  permissions: string[]
}

export const whoamiQuery = queryOptions({
  queryKey: ['session', 'whoami'],
  queryFn: () => unwrap(api.GET('/api/v1/auth/whoami')) as Promise<Whoami>,
  staleTime: 60_000,
  retry: false,
})

/** The signed-in account. Only use under the `_authenticated` layout, which loads it first. */
export function useSession(): Whoami {
  const { data } = useQuery(whoamiQuery)
  return data as Whoami
}

export function can(session: Whoami | undefined, permission?: string) {
  if (!permission) return true
  if (!session) return false
  return session.is_superuser || session.permissions.includes(permission)
}

export function initials(name: string) {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join('')
}

export async function signOut() {
  await api.POST('/api/v1/auth/logout')
}

/** Starts the Microsoft sign-in. The backend runs the whole OAuth flow and sets the session cookie. */
export function microsoftSignInUrl(redirect?: string) {
  const to =
    redirect && redirect.startsWith('/') && !redirect.startsWith('//')
      ? redirect
      : '/'
  return `/api/v1/auth/oauth/entra?redirect_to=${encodeURIComponent(to)}`
}
