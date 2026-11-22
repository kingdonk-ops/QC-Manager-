import { useState } from 'react'
import { Copy } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { useCurrentProject } from '@/stores/use-current-project'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Switch } from '@/components/ui/switch'
import { Page } from '@/components/layout/page'
import { NativeSelect } from '@/components/native-select'
import { StatusBadge } from '@/components/records/status-badge'
import {
  useDecide,
  useInvite,
  useInviteAction,
  useInvites,
  useListing,
  useMembers,
  useRequestQueue,
  useSetListing,
} from './api'

function Queue() {
  const { t } = useTranslation()
  const [status, setStatus] = useState('pending')
  const { data = [] } = useRequestQueue(status)
  const decide = useDecide()
  const [reasons, setReasons] = useState<Record<number, string>>({})
  return (
    <section className='grid content-start gap-2'>
      <div className='flex items-center gap-2'>
        <h3 className='me-auto text-sm font-semibold'>{t('lobby.requests')}</h3>
        <NativeSelect
          className='h-8 w-36'
          aria-label={t('lobby.status')}
          values={['pending', 'approved', 'rejected', 'withdrawn', 'all']}
          value={status}
          onChange={(e) => setStatus(e.target.value)}
        />
      </div>
      {data.map((r) => (
        <div key={r.id} className='grid gap-2 rounded-md border p-3 text-sm'>
          <div className='flex flex-wrap items-center gap-2'>
            <span className='me-auto font-medium'>
              {r.user_name}{' '}
              <span className='text-muted-foreground'>{r.user_email}</span>
            </span>
            <span className='font-mono text-xs'>{r.project_code}</span>
            <StatusBadge status={r.status} />
          </div>
          {r.message ? <p>{r.message}</p> : null}
          {r.status === 'pending' ? (
            <div className='flex flex-wrap gap-2'>
              <Button
                size='sm'
                onClick={() => decide.mutate({ id: r.id, approve: true })}
              >
                {t('lobby.approve')}
              </Button>
              <Input
                className='h-8 w-60'
                placeholder={t('lobby.reason')}
                maxLength={500}
                value={reasons[r.id] ?? ''}
                onChange={(e) =>
                  setReasons({ ...reasons, [r.id]: e.target.value })
                }
              />
              <Button
                size='sm'
                variant='outline'
                onClick={() =>
                  decide.mutate({
                    id: r.id,
                    approve: false,
                    reason: reasons[r.id],
                  })
                }
              >
                {t('lobby.reject')}
              </Button>
            </div>
          ) : r.rejection_reason ? (
            <p className='text-xs text-muted-foreground'>
              {r.rejection_reason}
            </p>
          ) : null}
        </div>
      ))}
      {!data.length ? (
        <p className='text-sm text-muted-foreground'>
          {t('lobby.no_requests')}
        </p>
      ) : null}
    </section>
  )
}

function ProjectAccess({ projectId }: { projectId: number }) {
  const { t } = useTranslation()
  const { data: listing } = useListing(projectId)
  const setListing = useSetListing(projectId)
  const { data: members = [] } = useMembers(projectId)
  const { data: invites = [] } = useInvites(projectId)
  const invite = useInvite(projectId)
  const action = useInviteAction()
  const [email, setEmail] = useState('')
  const [name, setName] = useState('')
  const [link, setLink] = useState('')
  return (
    <section className='grid content-start gap-4'>
      <label className='flex items-center gap-2 text-sm'>
        <Switch
          checked={Boolean(listing?.visible)}
          onCheckedChange={(v) => setListing.mutate(v)}
        />
        {t('lobby.listed')}
      </label>
      <form
        className='grid gap-2 rounded-md border p-3'
        onSubmit={(e) => {
          e.preventDefault()
          invite.mutate(
            { email, name },
            {
              onSuccess: (made) => {
                setLink(made.link)
                setEmail('')
                setName('')
              },
            }
          )
        }}
      >
        <h3 className='text-sm font-semibold'>{t('lobby.invite')}</h3>
        <div className='flex flex-wrap gap-2'>
          <Input
            type='email'
            required
            className='h-8 w-64'
            placeholder={t('lobby.email')}
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
          <Input
            className='h-8 w-48'
            placeholder={t('lobby.name_if_new')}
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <Button size='sm' type='submit' disabled={invite.isPending}>
            {t('lobby.send_invite')}
          </Button>
        </div>
        {link ? (
          <div className='flex items-center gap-2 text-xs'>
            <code className='truncate'>{link}</code>
            <Button
              size='icon'
              variant='ghost'
              type='button'
              aria-label={t('lobby.copy')}
              onClick={() => {
                void navigator.clipboard?.writeText(link)
                toast.success(t('lobby.copied'))
              }}
            >
              <Copy />
            </Button>
          </div>
        ) : null}
      </form>
      <div className='grid gap-1 text-sm'>
        <h3 className='font-semibold'>{t('lobby.pending_invites')}</h3>
        {invites.map((i) => (
          <div key={i.id} className='flex flex-wrap items-center gap-2'>
            <span className='me-auto'>{i.email}</span>
            <StatusBadge status={i.expired ? 'overdue' : i.status} />
            <span className='text-xs text-muted-foreground'>
              {new Date(i.expires_at).toLocaleDateString()}
            </span>
            <Button
              size='sm'
              variant='outline'
              onClick={() =>
                action.mutate(
                  { id: i.id, action: 'resend' },
                  { onSuccess: (r) => 'link' in r && setLink(String(r.link)) }
                )
              }
            >
              {t('lobby.resend')}
            </Button>
            <Button
              size='sm'
              variant='outline'
              onClick={() => action.mutate({ id: i.id, action: 'revoke' })}
            >
              {t('lobby.revoke')}
            </Button>
          </div>
        ))}
      </div>
      <div className='grid gap-1 text-sm'>
        <h3 className='font-semibold'>{t('lobby.members')}</h3>
        {members.map((m) => (
          <div key={`${m.via}-${m.user_id}`} className='flex gap-2'>
            <span className='me-auto'>
              {m.name} <span className='text-muted-foreground'>{m.email}</span>
            </span>
            <span className='text-xs text-muted-foreground'>
              {m.via === 'client_team'
                ? t('lobby.client_team')
                : t('lobby.direct')}
            </span>
          </div>
        ))}
      </div>
    </section>
  )
}

export default function AccessPage() {
  const { t } = useTranslation()
  const project = useCurrentProject()
  return (
    <Page
      title={t('lobby.access_title')}
      description={t('lobby.access_description')}
      projectScoped
    >
      <div className='grid gap-6 lg:grid-cols-2'>
        <Queue />
        {project ? (
          <ProjectAccess key={project.id} projectId={project.id} />
        ) : null}
      </div>
    </Page>
  )
}
