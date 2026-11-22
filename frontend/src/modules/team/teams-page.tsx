import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { ColDef, ICellRendererParams } from 'ag-grid-community'
import { Pencil, Plus, RefreshCw, Trash2, UserPlus } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { api, unwrap } from '@/api/client'
import type { components } from '@/api/schema'
import { handleServerError } from '@/lib/handle-server-error'
import { can, useSession } from '@/lib/session'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { ConfirmDialog } from '@/components/confirm-dialog'
import { DataGrid } from '@/components/data-grid'
import { Page } from '@/components/layout/page'
import { EntraTag } from '@/components/person-badges'
import { usePeople } from '../people/api'

type Team = components['schemas']['TeamRead']
type Member = components['schemas']['TeamMemberRead']
type TeamRole = Member['role']
const ROLES: TeamRole[] = ['member', 'lead', 'manager']

type TeamForm = { name: string; description: string; entra_group_id: string }

function TeamDialog({
  team,
  open,
  onOpenChange,
  onSaved,
}: {
  team: Team | null
  open: boolean
  onOpenChange: (open: boolean) => void
  onSaved: (id: number) => void
}) {
  const { t } = useTranslation()
  const save = useMutation({
    mutationFn: (form: TeamForm) => {
      const body = {
        name: form.name,
        description: form.description || null,
        entra_group_id: form.entra_group_id || null,
      }
      return team
        ? unwrap(
            api.PATCH('/api/v1/teams/{team_id}', {
              params: { path: { team_id: team.id } },
              body,
            })
          )
        : unwrap(api.POST('/api/v1/teams/', { body }))
    },
    onSuccess: (saved) => {
      onSaved(saved.id)
      onOpenChange(false)
    },
    onError: handleServerError,
  })

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {team ? `Edit ${team.name}` : t('teams.new')}
          </DialogTitle>
        </DialogHeader>
        <form
          id='team-form'
          className='grid gap-3'
          onSubmit={(e) => {
            e.preventDefault()
            const f = new FormData(e.currentTarget)
            save.mutate({
              name: String(f.get('name') ?? '').trim(),
              description: String(f.get('description') ?? '').trim(),
              entra_group_id: String(f.get('entra_group_id') ?? '').trim(),
            })
          }}
        >
          <div className='grid gap-1.5'>
            <Label htmlFor='name'>{t('teams.name')}</Label>
            <Input id='name' name='name' defaultValue={team?.name} required />
          </div>
          <div className='grid gap-1.5'>
            <Label htmlFor='description'>Description</Label>
            <Textarea
              id='description'
              name='description'
              defaultValue={team?.description ?? ''}
              rows={2}
            />
          </div>
          <div className='grid gap-1.5'>
            <Label htmlFor='entra_group_id'>{t('teams.group_id')}</Label>
            <Input
              id='entra_group_id'
              name='entra_group_id'
              className='font-mono'
              defaultValue={team?.entra_group_id ?? ''}
              placeholder='00000000-0000-0000-0000-000000000000'
            />
            <p className='text-xs text-muted-foreground'>
              Linked teams take their members from the Entra group at each
              sign-in and hourly sync. Leave empty to manage members here, e.g.
              for a client's portal users.
            </p>
          </div>
        </form>
        <DialogFooter>
          <Button variant='outline' onClick={() => onOpenChange(false)}>
            {t('common.cancel')}
          </Button>
          <Button type='submit' form='team-form' disabled={save.isPending}>
            {t('common.save')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function Members({
  teamId,
  canManage,
}: {
  teamId: number
  canManage: boolean
}) {
  const { t } = useTranslation()
  const session = useSession()
  const queryClient = useQueryClient()
  const [adding, setAdding] = useState<{ userId: string; role: TeamRole }>({
    userId: '',
    role: 'member',
  })
  const { data: team } = useQuery({
    queryKey: ['teams', teamId],
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/teams/{team_id}', {
          params: { path: { team_id: teamId } },
        })
      ),
  })
  const { data: people = [] } = usePeople(
    '',
    false,
    canManage && can(session, 'people.read')
  )
  const linked = Boolean(team?.entra_group_id)
  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ['teams'] })
    void queryClient.invalidateQueries({ queryKey: ['people'] })
  }

  const { mutate: setMember } = useMutation({
    mutationFn: ({ userId, role }: { userId: number; role: TeamRole }) =>
      unwrap(
        api.PUT('/api/v1/teams/{team_id}/members/{user_id}', {
          params: { path: { team_id: teamId, user_id: userId } },
          body: { role },
        })
      ),
    onSuccess: refresh,
    onError: (error) => {
      handleServerError(error)
      refresh()
    },
  })
  const { mutate: removeMember } = useMutation({
    mutationFn: (userId: number) =>
      unwrap(
        api.DELETE('/api/v1/teams/{team_id}/members/{user_id}', {
          params: { path: { team_id: teamId, user_id: userId } },
        })
      ),
    onSuccess: refresh,
    onError: handleServerError,
  })

  const columns = useMemo<ColDef<Member>[]>(
    () => [
      { field: 'name', headerName: t('teams.member'), flex: 1 },
      { field: 'email', headerName: t('teams.email'), flex: 1 },
      {
        field: 'role',
        headerName: t('teams.role'),
        width: 120,
        editable: canManage,
        cellEditor: 'agSelectCellEditor',
        cellEditorParams: { values: ROLES },
        cellClass: canManage
          ? 'cursor-pointer underline decoration-dotted'
          : undefined,
      },
      ...(canManage && !linked
        ? [
            {
              headerName: '',
              width: 48,
              sortable: false,
              filter: false,
              cellRenderer: (p: ICellRendererParams<Member>) =>
                p.data ? (
                  <button
                    aria-label='Remove'
                    className='text-muted-foreground hover:text-red-600'
                    onClick={() => removeMember(p.data!.user_id)}
                  >
                    <Trash2 className='size-4' />
                  </button>
                ) : null,
            } satisfies ColDef<Member>,
          ]
        : []),
    ],
    [canManage, linked, removeMember, t]
  )

  const memberIds = new Set(team?.members?.map((m) => m.user_id))
  const candidates = people.filter((p) => !memberIds.has(p.id))

  return (
    <div className='grid h-full grid-rows-[auto_1fr] gap-3'>
      {canManage && !linked ? (
        <form
          className='flex flex-wrap gap-2'
          onSubmit={(e) => {
            e.preventDefault()
            if (!adding.userId) return
            setMember(
              { userId: Number(adding.userId), role: adding.role },
              { onSuccess: () => setAdding({ userId: '', role: 'member' }) }
            )
          }}
        >
          <Select
            value={adding.userId}
            onValueChange={(userId) => setAdding({ ...adding, userId })}
          >
            <SelectTrigger size='sm' className='h-8 w-60'>
              <SelectValue placeholder='Choose a person' />
            </SelectTrigger>
            <SelectContent>
              {candidates.map((p) => (
                <SelectItem key={p.id} value={String(p.id)}>
                  {p.name}
                  <span className='text-muted-foreground'>
                    {' '}
                    · {p.account_type === 'staff' ? 'staff' : 'client'}
                  </span>
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select
            value={adding.role}
            onValueChange={(role) =>
              setAdding({ ...adding, role: role as TeamRole })
            }
          >
            <SelectTrigger size='sm' className='h-8 w-28'>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {ROLES.map((r) => (
                <SelectItem key={r} value={r}>
                  {r}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button size='sm' type='submit' disabled={!adding.userId}>
            <UserPlus /> Add
          </Button>
        </form>
      ) : linked ? (
        <p className='text-xs text-muted-foreground'>
          Members come from the Entra group. You can still set who leads the
          team.
        </p>
      ) : (
        <span />
      )}
      <DataGrid
        rowData={team?.members ?? []}
        columnDefs={columns}
        getRowId={(p) => String(p.data.user_id)}
        singleClickEdit
        onCellValueChanged={(e) => {
          if (e.data && e.newValue !== e.oldValue)
            setMember({ userId: e.data.user_id, role: e.newValue })
        }}
      />
    </div>
  )
}

export default function TeamsPage() {
  const { t } = useTranslation()
  const session = useSession()
  const queryClient = useQueryClient()
  const [selected, setSelected] = useState<number | null>(null)
  const [editing, setEditing] = useState<Team | null | 'new'>(null)
  const [deleting, setDeleting] = useState(false)

  const { data: teams } = useQuery({
    queryKey: ['teams', 'all'],
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/teams/', {
          params: { query: { items_per_page: 100 } },
        })
      ),
  })
  const current = teams?.data.find((team) => team.id === selected) ?? null

  const sync = useMutation({
    mutationFn: () => unwrap(api.POST('/api/v1/entra/sync')),
    onSuccess: (report) => {
      toast.success(
        `Synced ${report.teams_synced} teams: +${report.memberships_added} / -${report.memberships_removed}`
      )
      void queryClient.invalidateQueries({ queryKey: ['teams'] })
    },
    onError: handleServerError,
  })
  const remove = useMutation({
    mutationFn: (teamId: number) =>
      unwrap(
        api.DELETE('/api/v1/teams/{team_id}', {
          params: { path: { team_id: teamId } },
        })
      ),
    onSuccess: () => {
      setSelected(null)
      setDeleting(false)
      void queryClient.invalidateQueries({ queryKey: ['teams'] })
    },
    onError: handleServerError,
  })

  const teamColumns = useMemo<ColDef<Team>[]>(
    () => [
      {
        field: 'name',
        headerName: t('teams.name'),
        flex: 1,
        cellRenderer: (p: ICellRendererParams<Team>) => (
          <span className='flex items-center gap-2'>
            {p.value}
            {p.data?.entra_group_id ? <EntraTag /> : null}
          </span>
        ),
      },
      {
        field: 'member_count',
        headerName: t('teams.members'),
        width: 110,
        type: 'rightAligned',
      },
      {
        headerName: t('teams.source'),
        width: 130,
        valueGetter: (p) =>
          p.data?.entra_group_id ? t('teams.entra') : t('teams.manual'),
      },
    ],
    [t]
  )

  return (
    <Page
      title={t('teams.title')}
      description={t('teams.description')}
      actions={
        <>
          {can(session, 'entra.manage') ? (
            <Button
              size='sm'
              variant='outline'
              onClick={() => sync.mutate()}
              disabled={sync.isPending}
            >
              <RefreshCw
                className={sync.isPending ? 'animate-spin' : undefined}
              />{' '}
              {t('teams.sync')}
            </Button>
          ) : null}
          {can(session, 'team.create') ? (
            <Button size='sm' onClick={() => setEditing('new')}>
              <Plus /> {t('teams.new')}
            </Button>
          ) : null}
        </>
      }
    >
      <div className='grid gap-4 lg:grid-cols-[2fr_3fr]'>
        <div className='h-[520px]'>
          <DataGrid
            rowData={teams?.data ?? []}
            columnDefs={teamColumns}
            getRowId={(p) => String(p.data.id)}
            rowSelection={{
              mode: 'singleRow',
              checkboxes: false,
              enableClickSelection: true,
            }}
            onRowClicked={(e) => e.data && setSelected(e.data.id)}
            rowClass='cursor-pointer'
          />
        </div>
        <Card className='h-[520px] gap-3'>
          <CardHeader>
            <div className='flex items-start justify-between gap-2'>
              <div className='grid gap-1'>
                <CardTitle className='flex items-center gap-2 text-base'>
                  {current?.name ?? t('teams.members')}
                  {current?.entra_group_id ? <EntraTag /> : null}
                </CardTitle>
                {current?.description ? (
                  <CardDescription>{current.description}</CardDescription>
                ) : null}
                {current?.entra_group_id ? (
                  <CardDescription className='font-mono text-xs'>
                    {current.entra_group_id}
                  </CardDescription>
                ) : null}
              </div>
              {current ? (
                <div className='flex gap-1'>
                  {can(session, 'team.update') ? (
                    <Button
                      size='icon'
                      variant='ghost'
                      aria-label='Edit team'
                      onClick={() => setEditing(current)}
                    >
                      <Pencil className='size-4' />
                    </Button>
                  ) : null}
                  {can(session, 'team.delete') ? (
                    <Button
                      size='icon'
                      variant='ghost'
                      aria-label='Delete team'
                      onClick={() => setDeleting(true)}
                    >
                      <Trash2 className='size-4' />
                    </Button>
                  ) : null}
                </div>
              ) : null}
            </div>
          </CardHeader>
          <CardContent className='min-h-0 flex-1'>
            {current ? (
              <Members
                key={current.id}
                teamId={current.id}
                canManage={can(session, 'team.manage_members')}
              />
            ) : (
              <p className='text-sm text-muted-foreground'>{t('teams.pick')}</p>
            )}
          </CardContent>
        </Card>
      </div>

      <TeamDialog
        key={editing === 'new' ? 'new' : (editing?.id ?? 'closed')}
        team={editing === 'new' ? null : editing}
        open={editing !== null}
        onOpenChange={(open) => !open && setEditing(null)}
        onSaved={(id) => {
          setSelected(id)
          void queryClient.invalidateQueries({ queryKey: ['teams'] })
        }}
      />
      <ConfirmDialog
        open={deleting}
        onOpenChange={setDeleting}
        title={`Delete ${current?.name ?? 'team'}?`}
        desc='Its memberships are removed. Projects that use it as their client team lose portal access.'
        confirmText='Delete'
        destructive
        handleConfirm={() => current && remove.mutate(current.id)}
      />
    </Page>
  )
}
