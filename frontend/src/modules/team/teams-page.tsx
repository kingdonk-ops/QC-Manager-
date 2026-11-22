import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { ColDef } from 'ag-grid-community'
import { Plus, RefreshCw } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { api, unwrap } from '@/api/client'
import type { components } from '@/api/schema'
import { handleServerError } from '@/lib/handle-server-error'
import { can, useSession } from '@/lib/session'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { DataGrid } from '@/components/data-grid'
import { Page } from '@/components/layout/page'

type Team = components['schemas']['TeamRead']
type Member = components['schemas']['TeamMemberRead']

export default function TeamsPage() {
  const { t } = useTranslation()
  const session = useSession()
  const queryClient = useQueryClient()
  const [selected, setSelected] = useState<number | null>(null)
  const [draft, setDraft] = useState({ name: '', entra_group_id: '' })

  const { data: teams } = useQuery({
    queryKey: ['teams', 'all'],
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/teams/', {
          params: { query: { items_per_page: 100 } },
        })
      ),
  })
  const { data: detail } = useQuery({
    queryKey: ['teams', selected],
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/teams/{team_id}', {
          params: { path: { team_id: selected! } },
        })
      ),
    enabled: selected !== null,
  })

  const create = useMutation({
    mutationFn: () =>
      unwrap(
        api.POST('/api/v1/teams/', {
          body: {
            name: draft.name,
            entra_group_id: draft.entra_group_id || null,
          } as never,
        })
      ),
    onSuccess: () => {
      setDraft({ name: '', entra_group_id: '' })
      void queryClient.invalidateQueries({ queryKey: ['teams'] })
    },
    onError: handleServerError,
  })
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

  const teamColumns = useMemo<ColDef<Team>[]>(
    () => [
      { field: 'name', headerName: t('teams.name'), flex: 1 },
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
  const memberColumns = useMemo<ColDef<Member>[]>(
    () => [
      { field: 'name', headerName: t('teams.member'), flex: 1 },
      { field: 'email', headerName: t('teams.email'), flex: 1 },
      { field: 'role', headerName: t('teams.role'), width: 110 },
    ],
    [t]
  )

  return (
    <Page
      title={t('teams.title')}
      description={t('teams.description')}
      actions={
        can(session, 'entra.manage') ? (
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
        ) : null
      }
    >
      {can(session, 'team.create') ? (
        <form
          className='flex flex-wrap gap-2'
          onSubmit={(e) => {
            e.preventDefault()
            create.mutate()
          }}
        >
          <Input
            className='h-8 w-56'
            placeholder={t('teams.name')}
            value={draft.name}
            onChange={(e) => setDraft({ ...draft, name: e.target.value })}
            required
          />
          <Input
            className='h-8 w-80 font-mono'
            placeholder={t('teams.group_id')}
            value={draft.entra_group_id}
            onChange={(e) =>
              setDraft({ ...draft, entra_group_id: e.target.value })
            }
          />
          <Button size='sm' type='submit' disabled={create.isPending}>
            <Plus /> {t('teams.new')}
          </Button>
        </form>
      ) : null}
      <div className='grid gap-4 lg:grid-cols-2'>
        <div className='h-[480px]'>
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
          />
        </div>
        <Card className='gap-2'>
          <CardHeader>
            <CardTitle className='text-base'>
              {detail?.name ?? t('teams.members')}
            </CardTitle>
          </CardHeader>
          <CardContent className='h-[420px]'>
            {selected === null ? (
              <p className='text-sm text-muted-foreground'>{t('teams.pick')}</p>
            ) : (
              <DataGrid
                rowData={detail?.members ?? []}
                columnDefs={memberColumns}
                getRowId={(p) => String(p.data.user_id)}
              />
            )}
          </CardContent>
        </Card>
      </div>
    </Page>
  )
}
