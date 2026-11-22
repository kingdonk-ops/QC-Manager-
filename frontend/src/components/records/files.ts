import { csrfHeaders } from '@/api/client'
import type { components } from '@/api/schema'

export type StoredFile = components['schemas']['FileRead']

export function formatSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

export async function uploadFile(form: FormData): Promise<StoredFile> {
  const response = await fetch('/api/v1/files/', {
    method: 'POST',
    credentials: 'include',
    headers: csrfHeaders(),
    body: form,
  })
  const body = await response.json().catch(() => ({}))
  if (!response.ok)
    throw new Error(
      typeof body.detail === 'string' ? body.detail : 'Upload failed'
    )
  return body as StoredFile
}

export const fileUrl = (id: number, inline = false) =>
  `/api/v1/files/${id}/download${inline ? '?inline=true' : ''}`
