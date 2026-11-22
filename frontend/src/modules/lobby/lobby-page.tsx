import { useEffect, useState } from 'react'
import { useNavigate } from '@tanstack/react-router'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { useProjectStore } from '@/stores/project-store'
import { handleServerError } from '@/lib/handle-server-error'
import { useSession } from '@/lib/session'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Page } from '@/components/layout/page'
import { StatusBadge } from '@/components/records/status-badge'
import {
  lookup,
  useClaim,
  useFileRequest,
  useJoin,
  useLobbyProjects,
  useMyRequests,
  useWithdraw,
} from './api'

function RequestBox({
  label,
  onSend,
}: {
  label: string
  onSend: (message: string) => void
}) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const [message, setMessage] = useState('')
  if (!open)
    return (
      <Button size='sm' onClick={() => setOpen(true)}>
        {label}
      </Button>
    )
  return (
    <div className='grid w-full gap-2'>
      <Textarea
        aria-label={t('lobby.message')}
        placeholder={t('lobby.message')}
        value={message}
        maxLength={1000}
        onChange={(e) => setMessage(e.target.value)}
      />
      <Button size='sm' onClick={() => onSend(message)}>
        {t('lobby.send')}
      </Button>
    </div>
  )
}

export default function LobbyPage() {
  const { t } = useTranslation()
  const session = useSession()
  const navigate = useNavigate()
  const setProjectId = useProjectStore((s) => s.setProjectId)
  const internal = session.account_type === 'staff'
  const claim = useClaim()
  const { data: projects = [] } = useLobbyProjects()
  const { data: mine = [] } = useMyRequests()
  const file = useFileRequest()
  const withdraw = useWithdraw()
  const join = useJoin()
  const [code, setCode] = useState('')
  const [found, setFound] = useState<{
    id: number
    code: string
    name: string
  } | null>(null)

  const { mutate: claimInvites } = claim
  useEffect(() => {
    claimInvites(undefined, {
      onSuccess: (joined) => {
        if (joined.length) {
          toast.success(`${t('lobby.joined')} ${joined[0].project_code}`)
          setProjectId(joined[0].project_id)
        }
      },
    })
  }, [claimInvites, setProjectId, t])

  const open = (projectId: number) => {
    setProjectId(projectId)
    void navigate({ to: '/' })
  }

  return (
    <Page title={t('lobby.title')} description={t('lobby.description')}>
      <div className='grid gap-6 lg:grid-cols-[1fr_22rem]'>
        <div className='grid content-start gap-3'>
          {projects.map((p) => (
            <div
              key={p.id}
              className='flex flex-wrap items-center gap-3 rounded-md border p-3'
            >
              <div className='me-auto'>
                <div className='font-medium'>
                  <span className='font-mono text-xs text-muted-foreground'>
                    {p.code}
                  </span>{' '}
                  {p.name}
                </div>
                {p.client_name ? (
                  <div className='text-xs text-muted-foreground'>
                    {p.client_name}
                  </div>
                ) : null}
              </div>
              {p.invite_id ? (
                <Button
                  size='sm'
                  onClick={() =>
                    join.mutate(p.invite_id ?? 0, {
                      onSuccess: (j) => open(j.project_id),
                    })
                  }
                >
                  {t('lobby.join')}
                </Button>
              ) : p.request_status === 'pending' ? (
                <StatusBadge status='pending' />
              ) : (
                <RequestBox
                  label={t('lobby.request')}
                  onSend={(message) =>
                    file.mutate({
                      project_id: p.id,
                      message: message || undefined,
                    })
                  }
                />
              )}
            </div>
          ))}
          {!projects.length ? (
            <p className='text-sm text-muted-foreground'>
              {internal ? t('lobby.none_internal') : t('lobby.none_external')}
            </p>
          ) : null}
          {internal ? (
            <form
              className='flex flex-wrap items-end gap-2 rounded-md border p-3'
              onSubmit={async (e) => {
                e.preventDefault()
                try {
                  setFound(await lookup(code))
                } catch (error) {
                  setFound(null)
                  handleServerError(error)
                }
              }}
            >
              <div className='grid gap-1.5'>
                <label htmlFor='lobby-code' className='text-sm'>
                  {t('lobby.code')}
                </label>
                <Input
                  id='lobby-code'
                  className='h-8 w-44'
                  value={code}
                  onChange={(e) => setCode(e.target.value)}
                />
              </div>
              <Button size='sm' variant='outline' type='submit'>
                {t('lobby.find')}
              </Button>
              {found ? (
                <div className='flex w-full flex-wrap items-center gap-2'>
                  <span className='me-auto'>
                    {found.code} · {found.name}
                  </span>
                  <RequestBox
                    label={t('lobby.request')}
                    onSend={(message) =>
                      file.mutate(
                        { code: found.code, message: message || undefined },
                        { onSuccess: () => setFound(null) }
                      )
                    }
                  />
                </div>
              ) : null}
            </form>
          ) : null}
        </div>
        <section className='grid content-start gap-2'>
          <h3 className='text-sm font-semibold'>
            {t('lobby.active_requests')}
          </h3>
          {mine.map((r) => {
            const again = r.request_again_at
              ? new Date(r.request_again_at)
              : null
            const allowed = !again || again <= new Date()
            return (
              <div
                key={r.id}
                className='grid gap-1 rounded-md border p-2 text-sm'
              >
                <div className='flex items-center justify-between gap-2'>
                  <span>
                    {r.project_code} · {r.project_name}
                  </span>
                  <StatusBadge status={r.status} />
                </div>
                {r.rejection_reason ? (
                  <p className='text-xs text-muted-foreground'>
                    {r.rejection_reason}
                  </p>
                ) : null}
                {r.status === 'pending' ? (
                  <Button
                    size='sm'
                    variant='outline'
                    onClick={() => withdraw.mutate(r.id)}
                  >
                    {t('lobby.withdraw')}
                  </Button>
                ) : null}
                {r.status === 'approved' ? (
                  <Button size='sm' onClick={() => open(r.project_id)}>
                    {t('lobby.open')}
                  </Button>
                ) : null}
                {['rejected', 'withdrawn'].includes(r.status) ? (
                  <Button
                    size='sm'
                    variant='outline'
                    disabled={!allowed}
                    onClick={() => file.mutate({ project_id: r.project_id })}
                  >
                    {allowed
                      ? t('lobby.request_again')
                      : `${t('lobby.request_again_from')} ${again?.toLocaleString()}`}
                  </Button>
                ) : null}
              </div>
            )
          })}
          {!mine.length ? (
            <p className='text-sm text-muted-foreground'>
              {t('lobby.no_requests')}
            </p>
          ) : null}
        </section>
      </div>
    </Page>
  )
}
