/**
 * The typed API client. Types come from the backend's OpenAPI document:
 * after changing an endpoint, run `pnpm gen:api`.
 *
 * Auth is the backend's session cookie. Unsafe requests echo the readable
 * `csrf_token` cookie in `X-CSRF-Token`, which the backend checks.
 */
import createClient, { type Middleware } from 'openapi-fetch'
import { getCookie } from '@/lib/cookies'
import type { paths } from './schema'

const UNSAFE = new Set(['POST', 'PUT', 'PATCH', 'DELETE'])

const csrf: Middleware = {
  onRequest({ request }) {
    if (UNSAFE.has(request.method)) {
      const token = getCookie('csrf_token')
      if (token) request.headers.set('X-CSRF-Token', decodeURIComponent(token))
    }
    return request
  },
}

/** The CSRF header for a request made with plain `fetch` (multipart uploads, file downloads). */
export function csrfHeaders(): Record<string, string> {
  const token = getCookie('csrf_token')
  return token ? { 'X-CSRF-Token': decodeURIComponent(token) } : {}
}

export const api = createClient<paths>({ baseUrl: '', credentials: 'include' })
api.use(csrf)

export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: unknown
  ) {
    super(typeof detail === 'string' ? detail : `Request failed (${status})`)
  }
}

/** The response's data, or an `ApiError` carrying the backend's `detail`. */
export async function unwrap<T>(
  call: Promise<{ data?: T; error?: unknown; response: Response }>
): Promise<T> {
  const { data, error, response } = await call
  if (!response.ok) {
    const detail =
      error && typeof error === 'object' && 'detail' in error
        ? (error as { detail: unknown }).detail
        : error
    throw new ApiError(response.status, detail)
  }
  return data as T
}
