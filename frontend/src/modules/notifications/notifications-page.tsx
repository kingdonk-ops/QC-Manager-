import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from '@tanstack/react-router'
import { toast } from 'sonner'
import { api, unwrap } from '@/api/client'
import type { components } from '@/api/schema'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Switch } from '@/components/ui/switch'
import { Page } from '@/components/layout/page'
import { StatusBadge } from '@/components/records/status-badge'
import { useMarkRead, useNotifications, useReadAll } from './api'

type Pref = components['schemas']['PreferenceRow']

const LABELS: Record<string, string> = {
  assignment: 'Assigned to me',
  mention: '@mentions',
  status: 'Status changes and replies',
  approval: 'Approvals I need to give',
  due: 'Due date reminders',
  system: 'System alerts',
}

function Preferences() {
  const queryClient = useQueryClient()
  const { data: prefs = [] } = useQuery({
    queryKey: ['notifications', 'preferences'],
    queryFn: () => unwrap(api.GET('/api/v1/notifications/preferences')),
  })
  const save = useMutation({
    mutationFn: (preferences: Pref[]) =>
      unwrap(
        api.PUT('/api/v1/notifications/preferences', { body: { preferences } })
      ),
    onSuccess: (data) => {
      queryClient.setQueryData(['notifications', 'preferences'], data)
      toast.success('Preferences saved')
    },
  })
  const set = (category: string, field: 'in_app' | 'email', value: boolean) =>
    save.mutate(
      prefs.map((p) => (p.category === category ? { ...p, [field]: value } : p))
    )

  return (
    <Card>
      <CardHeader>
        <CardTitle className='text-base'>Preferences</CardTitle>
      </CardHeader>
      <CardContent className='grid gap-2 text-sm'>
        <div className='grid grid-cols-[1fr_auto_auto] gap-x-6 gap-y-3'>
          <span />
          <span className='text-xs text-muted-foreground'>In app</span>
          <span className='text-xs text-muted-foreground'>Email</span>
          {prefs.map((p) => (
            <div key={p.category} className='contents'>
              <span>{LABELS[p.category] ?? p.category}</span>
              <Switch
                checked={p.in_app}
                onCheckedChange={(v) => set(p.category, 'in_app', v)}
              />
              <Switch
                checked={p.email}
                onCheckedChange={(v) => set(p.category, 'email', v)}
              />
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}

export default function NotificationsPage() {
  const navigate = useNavigate()
  const { data } = useNotifications()
  const markRead = useMarkRead()
  const readAll = useReadAll()

  return (
    <Page
      title='Notifications'
      description='Assignments, mentions, approvals and status changes from every module.'
      actions={
        <Button size='sm' variant='outline' onClick={() => readAll.mutate()}>
          Mark all read
        </Button>
      }
    >
      <div className='grid gap-4 lg:grid-cols-[2fr_1fr]'>
        <Card className='py-0'>
          <CardContent className='p-0'>
            {data?.data.length ? null : (
              <p className='p-6 text-sm text-muted-foreground'>Nothing yet.</p>
            )}
            {data?.data.map((n) => (
              <div
                key={n.id}
                className={cn(
                  'flex items-start gap-3 border-b px-4 py-3',
                  !n.read_at && 'bg-blue-500/5'
                )}
              >
                <div className='grid flex-1 gap-0.5'>
                  <button
                    className={cn(
                      'text-start text-sm hover:underline',
                      !n.read_at && 'font-medium'
                    )}
                    onClick={() => {
                      if (!n.read_at) markRead.mutate({ id: n.id, read: true })
                      if (n.link) void navigate({ to: n.link as never })
                    }}
                  >
                    {n.title}
                  </button>
                  {n.body ? (
                    <p className='text-xs text-muted-foreground'>{n.body}</p>
                  ) : null}
                  <span className='text-[11px] text-muted-foreground'>
                    {new Date(n.created_at).toLocaleString()}
                  </span>
                </div>
                <StatusBadge status={n.category} />
                <Button
                  size='sm'
                  variant='ghost'
                  className='h-7 text-xs'
                  onClick={() =>
                    markRead.mutate({ id: n.id, read: !n.read_at })
                  }
                >
                  {n.read_at ? 'Mark unread' : 'Mark read'}
                </Button>
              </div>
            ))}
          </CardContent>
        </Card>
        <Preferences />
      </div>
    </Page>
  )
}
