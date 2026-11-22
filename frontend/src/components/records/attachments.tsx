import { useRef } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Download, Eye, Paperclip, Trash2, Upload } from 'lucide-react'
import { toast } from 'sonner'
import { api, unwrap } from '@/api/client'
import { handleServerError } from '@/lib/handle-server-error'
import { can, useSession } from '@/lib/session'
import { Button } from '@/components/ui/button'
import { fileUrl, formatSize, uploadFile } from './files'

/** Files attached to one record, with upload. */
export function Attachments({
  projectId,
  entityType,
  entityId,
}: {
  projectId: number
  entityType: string
  entityId: number
}) {
  const session = useSession()
  const queryClient = useQueryClient()
  const input = useRef<HTMLInputElement>(null)
  const key = ['files', projectId, entityType, entityId]
  const { data } = useQuery({
    queryKey: key,
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/files/', {
          params: {
            query: {
              project_id: projectId,
              entity_type: entityType,
              entity_id: entityId,
            },
          },
        })
      ),
  })
  const upload = useMutation({
    mutationFn: async (files: FileList) => {
      for (const file of Array.from(files)) {
        const form = new FormData()
        form.set('file', file)
        form.set('project_id', String(projectId))
        form.set('entity_type', entityType)
        form.set('entity_id', String(entityId))
        await uploadFile(form)
      }
    },
    onSuccess: () => {
      toast.success('Uploaded')
      void queryClient.invalidateQueries({ queryKey: key })
    },
    onError: handleServerError,
  })
  const remove = useMutation({
    mutationFn: (id: number) =>
      unwrap(
        api.DELETE('/api/v1/files/{file_id}', {
          params: { path: { file_id: id } },
        })
      ),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: key }),
    onError: handleServerError,
  })

  const files = data?.data ?? []
  return (
    <div className='grid gap-2'>
      {can(session, 'files.upload') ? (
        <>
          <input
            ref={input}
            type='file'
            multiple
            hidden
            onChange={(e) =>
              e.target.files?.length && upload.mutate(e.target.files)
            }
          />
          <Button
            size='sm'
            variant='outline'
            className='w-fit'
            onClick={() => input.current?.click()}
            disabled={upload.isPending}
          >
            <Upload /> Attach files
          </Button>
        </>
      ) : null}
      {files.length === 0 ? (
        <p className='text-sm text-muted-foreground'>No attachments.</p>
      ) : null}
      {files.map((f) => (
        <div
          key={f.id}
          className='flex items-center gap-2 rounded-md border px-3 py-2 text-sm'
        >
          <Paperclip className='size-4 text-muted-foreground' />
          <span className='flex-1 truncate'>
            {f.name}
            <span className='text-xs text-muted-foreground'>
              {' '}
              · {formatSize(f.size)}
              {f.revision > 1 ? ` · rev ${f.revision}` : ''}
            </span>
          </span>
          <a
            href={fileUrl(f.id, true)}
            target='_blank'
            rel='noreferrer'
            aria-label='Preview'
          >
            <Eye className='size-4' />
          </a>
          <a href={fileUrl(f.id)} aria-label='Download'>
            <Download className='size-4' />
          </a>
          {f.uploaded_by_id === session.id || can(session, 'files.delete') ? (
            <button aria-label='Delete' onClick={() => remove.mutate(f.id)}>
              <Trash2 className='size-4 text-muted-foreground hover:text-red-600' />
            </button>
          ) : null}
        </div>
      ))}
    </div>
  )
}
