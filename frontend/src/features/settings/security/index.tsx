import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Laptop, Smartphone } from 'lucide-react'
import { toast } from 'sonner'
import { api, unwrap } from '@/api/client'
import { handleServerError } from '@/lib/handle-server-error'
import { useSession } from '@/lib/session'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Separator } from '@/components/ui/separator'
import { PasswordInput } from '@/components/password-input'
import { ContentSection } from '../components/content-section'

type SessionInfo = {
  id: string
  device?: { browser?: string; os?: string; is_mobile?: boolean } | null
  ip?: string | null
  created_at: string
  last_activity: string
  current: boolean
}

function ChangePassword() {
  const change = useMutation({
    mutationFn: (body: { current_password: string; new_password: string }) =>
      unwrap(api.POST('/api/v1/auth/change-password', { body })),
    onSuccess: () =>
      toast.success('Password changed. Your other sessions were signed out.'),
    onError: handleServerError,
  })

  return (
    <form
      className='grid gap-3'
      onSubmit={(e) => {
        e.preventDefault()
        const form = new FormData(e.currentTarget)
        const next = String(form.get('new') ?? '')
        if (next !== String(form.get('confirm') ?? '')) {
          toast.error('The new passwords do not match.')
          return
        }
        change.mutate(
          {
            current_password: String(form.get('current') ?? ''),
            new_password: next,
          },
          { onSuccess: () => (e.target as HTMLFormElement).reset() }
        )
      }}
    >
      <h4 className='font-medium'>Change password</h4>
      <div className='grid gap-1.5'>
        <Label htmlFor='current'>Current password</Label>
        <PasswordInput
          id='current'
          name='current'
          autoComplete='current-password'
          required
        />
      </div>
      <div className='grid grid-cols-2 gap-3'>
        <div className='grid gap-1.5'>
          <Label htmlFor='new'>New password</Label>
          <PasswordInput
            id='new'
            name='new'
            autoComplete='new-password'
            required
          />
        </div>
        <div className='grid gap-1.5'>
          <Label htmlFor='confirm'>Confirm new password</Label>
          <PasswordInput
            id='confirm'
            name='confirm'
            autoComplete='new-password'
            required
          />
        </div>
      </div>
      <Button type='submit' className='w-fit' disabled={change.isPending}>
        Change password
      </Button>
    </form>
  )
}

function Sessions() {
  const queryClient = useQueryClient()
  const { data: sessions = [] } = useQuery({
    queryKey: ['auth', 'sessions'],
    queryFn: async () =>
      (await unwrap(api.GET('/api/v1/auth/sessions'))) as SessionInfo[],
  })
  const revoke = useMutation({
    mutationFn: async (id: string) => {
      const response = await fetch(
        `/api/v1/auth/sessions/${encodeURIComponent(id)}`,
        {
          method: 'DELETE',
          credentials: 'include',
          headers: {
            'X-CSRF-Token': decodeURIComponent(
              document.cookie.match(/(?:^|; )csrf_token=([^;]*)/)?.[1] ?? ''
            ),
          },
        }
      )
      if (!response.ok) throw new Error('Could not sign that session out')
    },
    onSuccess: () =>
      void queryClient.invalidateQueries({ queryKey: ['auth', 'sessions'] }),
    onError: handleServerError,
  })

  return (
    <div className='grid gap-3'>
      <h4 className='font-medium'>Where you're signed in</h4>
      {sessions.map((s) => (
        <div
          key={s.id}
          className='flex items-center gap-3 rounded-md border px-3 py-2 text-sm'
        >
          {s.device?.is_mobile ? (
            <Smartphone className='size-4' />
          ) : (
            <Laptop className='size-4' />
          )}
          <div className='grid flex-1'>
            <span className='font-medium'>
              {[s.device?.browser, s.device?.os].filter(Boolean).join(' on ') ||
                'Unknown device'}
              {s.current ? (
                <Badge variant='secondary' className='ms-2'>
                  This device
                </Badge>
              ) : null}
            </span>
            <span className='text-xs text-muted-foreground'>
              {s.ip ?? 'unknown address'} · active{' '}
              {new Date(s.last_activity).toLocaleString()}
            </span>
          </div>
          {!s.current ? (
            <Button
              size='sm'
              variant='outline'
              onClick={() => revoke.mutate(s.id)}
            >
              Sign out
            </Button>
          ) : null}
        </div>
      ))}
    </div>
  )
}

export function SettingsSecurity() {
  const session = useSession()
  return (
    <ContentSection
      title='Sign-in & security'
      desc='How you sign in, and the devices signed in as you.'
    >
      <div className='grid gap-6'>
        {session.sign_in_method === 'entra' ? (
          <Alert>
            <AlertDescription>
              You sign in with your work Microsoft account. Your password,
              multi-factor authentication and account recovery are managed by
              Microsoft, not here.
            </AlertDescription>
          </Alert>
        ) : (
          <ChangePassword />
        )}
        <Separator />
        <Sessions />
      </div>
    </ContentSection>
  )
}
