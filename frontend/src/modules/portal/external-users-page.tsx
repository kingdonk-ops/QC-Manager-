import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { ColDef } from 'ag-grid-community'
import { Send } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { api, unwrap } from '@/api/client'
import type { components } from '@/api/schema'
import { handleServerError } from '@/lib/handle-server-error'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { DataGrid } from '@/components/data-grid'
import { Page } from '@/components/layout/page'

type ExternalUser = components['schemas']['ExternalUserRead']

export default function ExternalUsersPage() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [draft, setDraft] = useState({ name: '', email: '' })
  const { data: users = [] } = useQuery({
    queryKey: ['portal', 'users'],
    queryFn: () => unwrap(api.GET('/api/v1/portal/users')),
  })

  const invite = useMutation({
    mutationFn: () =>
      unwrap(
        api.POST('/api/v1/portal/invitations', {
          body: { ...draft, team_ids: [] },
        })
      ),
    onSuccess: () => {
      toast.success(`Invitation sent to ${draft.email}`)
      setDraft({ name: '', email: '' })
      void queryClient.invalidateQueries({ queryKey: ['portal', 'users'] })
    },
    onError: handleServerError,
  })
  const { mutate: resend } = useMutation({
    mutationFn: (user_id: number) =>
      unwrap(
        api.POST('/api/v1/portal/users/{user_id}/resend-invitation', {
          params: { path: { user_id } },
        })
      ),
    onSuccess: () => toast.success('Invitation sent'),
    onError: handleServerError,
  })

  const columns = useMemo<ColDef<ExternalUser>[]>(
    () => [
      { field: 'name', headerName: t('portal.name'), flex: 1 },
      { field: 'email', headerName: t('portal.email'), flex: 1 },
      {
        headerName: t('portal.teams'),
        flex: 1,
        valueGetter: (p) => p.data?.teams?.join(', '),
      },
      { field: 'activated', headerName: t('portal.activated'), width: 130 },
      {
        headerName: '',
        width: 110,
        sortable: false,
        filter: false,
        cellRenderer: (p: { data?: ExternalUser }) =>
          p.data && !p.data.activated ? (
            <Button
              size='sm'
              variant='ghost'
              className='h-7'
              onClick={() => resend(p.data!.id)}
            >
              {t('portal.resend')}
            </Button>
          ) : null,
      },
    ],
    [resend, t]
  )

  return (
    <Page title={t('portal.title')} description={t('portal.description')}>
      <form
        className='flex flex-wrap gap-2'
        onSubmit={(e) => {
          e.preventDefault()
          invite.mutate()
        }}
      >
        <Input
          className='h-8 w-56'
          placeholder={t('portal.name')}
          value={draft.name}
          onChange={(e) => setDraft({ ...draft, name: e.target.value })}
          required
        />
        <Input
          className='h-8 w-72'
          type='email'
          placeholder={t('portal.email')}
          value={draft.email}
          onChange={(e) => setDraft({ ...draft, email: e.target.value })}
          required
        />
        <Button size='sm' type='submit' disabled={invite.isPending}>
          <Send /> {t('portal.invite')}
        </Button>
      </form>
      <div className='h-[480px]'>
        <DataGrid
          rowData={users}
          columnDefs={columns}
          getRowId={(p) => String(p.data.id)}
        />
      </div>
    </Page>
  )
}
