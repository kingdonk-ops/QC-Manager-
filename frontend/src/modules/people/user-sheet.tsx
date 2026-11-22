import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Link } from '@tanstack/react-router'
import { toast } from 'sonner'
import { api, unwrap } from '@/api/client'
import { handleServerError } from '@/lib/handle-server-error'
import { can, initials, useSession } from '@/lib/session'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Separator } from '@/components/ui/separator'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import {
  AccountTypeBadge,
  EntraTag,
  SignInBadge,
} from '@/components/person-badges'
import { useRoleOptions, type Person } from './api'

export function UserSheet({
  person,
  onClose,
}: {
  person: Person | null
  onClose: () => void
}) {
  const session = useSession()
  const queryClient = useQueryClient()
  const canAssign = can(session, 'role.assign')
  const { data: roles = [] } = useRoleOptions(can(session, 'role.read'))
  const refresh = () =>
    void queryClient.invalidateQueries({ queryKey: ['people'] })

  const toggleRole = useMutation({
    mutationFn: async ({ roleId, held }: { roleId: number; held: boolean }) => {
      const params = {
        params: { path: { role_id: roleId, user_id: person!.id } },
      }
      return held
        ? unwrap(api.DELETE('/api/v1/roles/{role_id}/users/{user_id}', params))
        : unwrap(api.POST('/api/v1/roles/{role_id}/users/{user_id}', params))
    },
    onSuccess: refresh,
    onError: handleServerError,
  })
  const setActive = useMutation({
    mutationFn: (active: boolean) =>
      unwrap(
        api.POST(
          active
            ? '/api/v1/people/{user_id}/reactivate'
            : '/api/v1/people/{user_id}/deactivate',
          { params: { path: { user_id: person!.id } } }
        )
      ),
    onSuccess: (p) => {
      toast.success(
        p.active ? 'Account reactivated' : 'Account deactivated and signed out'
      )
      refresh()
      onClose()
    },
    onError: handleServerError,
  })

  const heldIds = new Set(person?.roles?.map((r) => r.id))

  return (
    <Sheet open={person !== null} onOpenChange={(open) => !open && onClose()}>
      <SheetContent className='w-full gap-0 sm:max-w-md'>
        {person ? (
          <>
            <SheetHeader>
              <div className='flex items-center gap-3'>
                <Avatar className='size-11'>
                  <AvatarFallback>{initials(person.name)}</AvatarFallback>
                </Avatar>
                <div className='grid gap-0.5'>
                  <SheetTitle>{person.name}</SheetTitle>
                  <SheetDescription>{person.email}</SheetDescription>
                </div>
              </div>
              <div className='flex flex-wrap gap-1.5 pt-1'>
                <AccountTypeBadge type={person.account_type} />
                <SignInBadge method={person.sign_in_method} />
                {person.is_superuser ? <Badge>Superuser</Badge> : null}
                {!person.active ? (
                  <Badge variant='destructive'>Deactivated</Badge>
                ) : null}
                {!person.activated ? (
                  <Badge variant='outline'>Invitation pending</Badge>
                ) : null}
              </div>
            </SheetHeader>

            <div className='grid gap-5 overflow-y-auto px-4 pb-6'>
              <section className='grid gap-2'>
                <h4 className='text-sm font-medium'>Roles</h4>
                {roles.map((role) => {
                  const held = heldIds.has(role.id)
                  const managed = Boolean(role.entra_app_role)
                  return (
                    <label
                      key={role.id}
                      className='flex items-start gap-3 rounded-md border px-3 py-2 text-sm'
                    >
                      <Checkbox
                        checked={held}
                        disabled={!canAssign || managed || toggleRole.isPending}
                        onCheckedChange={() =>
                          toggleRole.mutate({ roleId: role.id, held })
                        }
                        className='mt-0.5'
                      />
                      <span className='grid flex-1 gap-0.5'>
                        <span className='flex items-center gap-2 font-medium'>
                          {role.name}
                          {managed ? <EntraTag /> : null}
                        </span>
                        <span className='text-xs text-muted-foreground'>
                          {managed
                            ? `Granted by the Entra app role ${role.entra_app_role}; change it in Entra.`
                            : (role.description ?? 'Assigned here.')}
                        </span>
                      </span>
                    </label>
                  )
                })}
              </section>

              <section className='grid gap-2'>
                <div className='flex items-center justify-between'>
                  <h4 className='text-sm font-medium'>Teams</h4>
                  <Link
                    to='/$'
                    params={{ _splat: 'teams' }}
                    className='text-xs underline'
                  >
                    Manage teams
                  </Link>
                </div>
                {person.teams?.length ? (
                  person.teams.map((team) => (
                    <div
                      key={team.id}
                      className='flex items-center justify-between rounded-md border px-3 py-2 text-sm'
                    >
                      <span className='flex items-center gap-2'>
                        {team.name}
                        {team.entra_managed ? <EntraTag /> : null}
                      </span>
                      <Badge variant='outline'>{team.role}</Badge>
                    </div>
                  ))
                ) : (
                  <p className='text-sm text-muted-foreground'>
                    Not in any team.
                  </p>
                )}
              </section>

              {can(session, 'people.manage') && person.id !== session.id ? (
                <>
                  <Separator />
                  <section className='grid gap-2'>
                    <h4 className='text-sm font-medium'>Account</h4>
                    <p className='text-xs text-muted-foreground'>
                      {person.active
                        ? 'Deactivating signs them out everywhere and blocks sign-in. Nothing is deleted.'
                        : 'This account cannot sign in.'}
                      {person.sign_in_method === 'entra'
                        ? ' Staff should also be disabled in Entra ID.'
                        : ''}
                    </p>
                    <Button
                      variant={person.active ? 'destructive' : 'default'}
                      className='w-fit'
                      onClick={() => setActive.mutate(!person.active)}
                      disabled={setActive.isPending}
                    >
                      {person.active
                        ? 'Deactivate account'
                        : 'Reactivate account'}
                    </Button>
                  </section>
                </>
              ) : null}
            </div>
          </>
        ) : null}
      </SheetContent>
    </Sheet>
  )
}
