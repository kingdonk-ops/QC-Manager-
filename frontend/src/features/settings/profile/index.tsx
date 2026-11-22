import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useMyProfile } from '@/modules/people/api'
import { toast } from 'sonner'
import { api, unwrap } from '@/api/client'
import { handleServerError } from '@/lib/handle-server-error'
import { initials } from '@/lib/session'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  AccountTypeBadge,
  EntraTag,
  SignInBadge,
} from '@/components/person-badges'
import { ContentSection } from '../components/content-section'

function Field({
  label,
  children,
}: {
  label: string
  children: React.ReactNode
}) {
  return (
    <div className='grid gap-1'>
      <p className='text-xs font-medium text-muted-foreground'>{label}</p>
      <div className='text-sm'>{children}</div>
    </div>
  )
}

export function SettingsProfile() {
  const { data: me } = useMyProfile()
  const queryClient = useQueryClient()
  const [name, setName] = useState<string | null>(null)
  const save = useMutation({
    mutationFn: (value: string) =>
      unwrap(
        api.PATCH('/api/v1/users/{username}', {
          params: { path: { username: me!.username } },
          body: { name: value },
        })
      ),
    onSuccess: () => {
      toast.success('Profile saved')
      setName(null)
      void queryClient.invalidateQueries({ queryKey: ['people'] })
      void queryClient.invalidateQueries({ queryKey: ['session'] })
    },
    onError: handleServerError,
  })

  if (!me) return null
  const editing = name ?? me.name

  return (
    <ContentSection
      title='Profile'
      desc='Who you are in the app, and what you have access to.'
    >
      <div className='grid gap-6'>
        <div className='flex items-center gap-4'>
          <Avatar className='size-14'>
            <AvatarFallback className='text-lg'>
              {initials(me.name)}
            </AvatarFallback>
          </Avatar>
          <div className='grid gap-1'>
            <p className='text-lg font-semibold'>{me.name}</p>
            <div className='flex gap-1.5'>
              <AccountTypeBadge type={me.account_type} />
              <SignInBadge method={me.sign_in_method} />
              {me.is_superuser ? <Badge>Superuser</Badge> : null}
            </div>
          </div>
        </div>

        <form
          className='grid gap-1.5'
          onSubmit={(e) => {
            e.preventDefault()
            save.mutate(editing.trim())
          }}
        >
          <Label htmlFor='name'>Display name</Label>
          <div className='flex gap-2'>
            <Input
              id='name'
              value={editing}
              onChange={(e) => setName(e.target.value)}
              minLength={2}
            />
            <Button
              type='submit'
              disabled={save.isPending || editing.trim() === me.name}
            >
              Save
            </Button>
          </div>
        </form>

        <div className='grid grid-cols-2 gap-4'>
          <Field label='Email'>{me.email}</Field>
          <Field label='Username'>
            <span className='font-mono'>{me.username}</span>
          </Field>
          <Field label='Member since'>
            {me.created_at ? new Date(me.created_at).toLocaleDateString() : '—'}
          </Field>
          <Field label='Signs in with'>
            {me.sign_in_method === 'entra'
              ? 'Your work Microsoft account'
              : 'Email and password'}
          </Field>
        </div>

        <Field label='Roles'>
          <div className='flex flex-wrap gap-1.5'>
            {me.roles?.length ? (
              me.roles.map((role) => (
                <Badge key={role.id} variant='secondary' className='gap-1.5'>
                  {role.name}
                  {role.entra_app_role ? <EntraTag /> : null}
                </Badge>
              ))
            ) : (
              <span className='text-muted-foreground'>No roles yet</span>
            )}
          </div>
        </Field>

        <Field label='Teams'>
          <div className='grid gap-1.5'>
            {me.teams?.length ? (
              me.teams.map((team) => (
                <div
                  key={team.id}
                  className='flex items-center justify-between rounded-md border px-3 py-2'
                >
                  <span className='flex items-center gap-2'>
                    {team.name}
                    {team.entra_managed ? <EntraTag /> : null}
                  </span>
                  <Badge variant='outline'>{team.role}</Badge>
                </div>
              ))
            ) : (
              <span className='text-muted-foreground'>Not in any team</span>
            )}
          </div>
        </Field>
        <p className='text-xs text-muted-foreground'>
          Roles and teams tagged Entra come from your Microsoft account and are
          changed by your IT administrator.
        </p>
      </div>
    </ContentSection>
  )
}
