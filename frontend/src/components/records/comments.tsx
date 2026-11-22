import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useLocation } from '@tanstack/react-router'
import { CheckCircle2, CornerDownRight, RotateCcw, Trash2 } from 'lucide-react'
import { api, unwrap } from '@/api/client'
import type { components } from '@/api/schema'
import { handleServerError } from '@/lib/handle-server-error'
import { can, initials, useSession } from '@/lib/session'
import { cn } from '@/lib/utils'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'

type CommentRead = components['schemas']['CommentRead']

function Body({ text }: { text: string }) {
  return (
    <p className='text-sm whitespace-pre-wrap'>
      {text.split(/(@[a-z0-9_]{2,32})/g).map((part, i) =>
        part.startsWith('@') ? (
          <span
            key={i}
            className='font-medium text-blue-600 dark:text-blue-400'
          >
            {part}
          </span>
        ) : (
          part
        )
      )}
    </p>
  )
}

/** Threaded comments on one record. `@username` notifies that person. */
export function Comments({
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
  const { href } = useLocation()
  const [draft, setDraft] = useState('')
  const [replying, setReplying] = useState<number | null>(null)
  const [reply, setReply] = useState('')
  const key = ['comments', projectId, entityType, entityId]
  const refresh = () => void queryClient.invalidateQueries({ queryKey: key })
  const link = { params: { query: { link: href } } }

  const { data: threads = [] } = useQuery({
    queryKey: key,
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/comments/', {
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
  const post = useMutation({
    mutationFn: () =>
      unwrap(
        api.POST('/api/v1/comments/', {
          ...link,
          body: {
            project_id: projectId,
            entity_type: entityType,
            entity_id: entityId,
            body: draft,
            attachment_ids: [],
          },
        })
      ),
    onSuccess: () => {
      setDraft('')
      refresh()
    },
    onError: handleServerError,
  })
  const answer = useMutation({
    mutationFn: (id: number) =>
      unwrap(
        api.POST('/api/v1/comments/{comment_id}/reply', {
          params: { path: { comment_id: id }, query: { link: href } },
          body: { body: reply, attachment_ids: [] },
        })
      ),
    onSuccess: () => {
      setReply('')
      setReplying(null)
      refresh()
    },
    onError: handleServerError,
  })
  const resolve = useMutation({
    mutationFn: ({ id, resolved }: { id: number; resolved: boolean }) =>
      unwrap(
        api.PATCH('/api/v1/comments/{comment_id}/resolve', {
          params: { path: { comment_id: id } },
          body: { resolved },
        })
      ),
    onSuccess: refresh,
    onError: handleServerError,
  })
  const remove = useMutation({
    mutationFn: (id: number) =>
      unwrap(
        api.DELETE('/api/v1/comments/{comment_id}', {
          params: { path: { comment_id: id } },
        })
      ),
    onSuccess: refresh,
    onError: handleServerError,
  })

  const mine = (c: CommentRead) =>
    c.author_id === session.id || can(session, 'comments.update')

  const entry = (c: CommentRead, root?: CommentRead) => (
    <div key={c.id} className={cn('flex gap-2', root && 'ms-8')}>
      <Avatar className='size-7'>
        <AvatarFallback className='text-[10px]'>
          {initials(c.author_name ?? '?')}
        </AvatarFallback>
      </Avatar>
      <div className='grid flex-1 gap-0.5'>
        <div className='flex items-center gap-2 text-xs text-muted-foreground'>
          <span className='font-medium text-foreground'>
            {c.author_name ?? 'Former user'}
          </span>
          {c.created_at ? new Date(c.created_at).toLocaleString() : null}
          {c.edited ? '· edited' : null}
          {!root && c.resolved ? (
            <Badge variant='secondary'>Resolved</Badge>
          ) : null}
        </div>
        <Body text={c.body} />
        <div className='flex gap-3 text-xs text-muted-foreground'>
          {!root && can(session, 'comments.create') ? (
            <button
              className='flex items-center gap-1 hover:text-foreground'
              onClick={() => setReplying(c.id)}
            >
              <CornerDownRight className='size-3' /> Reply
            </button>
          ) : null}
          {!root && mine(c) ? (
            <button
              className='flex items-center gap-1 hover:text-foreground'
              onClick={() =>
                resolve.mutate({ id: c.id, resolved: !c.resolved })
              }
            >
              {c.resolved ? (
                <RotateCcw className='size-3' />
              ) : (
                <CheckCircle2 className='size-3' />
              )}
              {c.resolved ? 'Reopen' : 'Resolve'}
            </button>
          ) : null}
          {mine(c) ? (
            <button
              className='flex items-center gap-1 hover:text-red-600'
              onClick={() => remove.mutate(c.id)}
            >
              <Trash2 className='size-3' /> Delete
            </button>
          ) : null}
        </div>
      </div>
    </div>
  )

  return (
    <div className='grid gap-4'>
      {threads.length === 0 ? (
        <p className='text-sm text-muted-foreground'>No comments yet.</p>
      ) : null}
      {threads.map((t) => (
        <div
          key={t.id}
          className={cn(
            'grid gap-3 rounded-md border p-3',
            t.resolved && 'opacity-60'
          )}
        >
          {entry(t)}
          {t.replies?.map((r) => entry(r, t))}
          {replying === t.id ? (
            <div className='ms-8 grid gap-2'>
              <Textarea
                value={reply}
                onChange={(e) => setReply(e.target.value)}
                rows={2}
                autoFocus
              />
              <div className='flex gap-2'>
                <Button
                  size='sm'
                  disabled={!reply.trim()}
                  onClick={() => answer.mutate(t.id)}
                >
                  Reply
                </Button>
                <Button
                  size='sm'
                  variant='ghost'
                  onClick={() => setReplying(null)}
                >
                  Cancel
                </Button>
              </div>
            </div>
          ) : null}
        </div>
      ))}
      {can(session, 'comments.create') ? (
        <div className='grid gap-2'>
          <Textarea
            placeholder='Add a comment. Type @username to notify someone.'
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            rows={3}
          />
          <Button
            size='sm'
            className='w-fit'
            disabled={!draft.trim() || post.isPending}
            onClick={() => post.mutate()}
          >
            Comment
          </Button>
        </div>
      ) : null}
    </div>
  )
}
