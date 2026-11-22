import { useMemo, useState } from 'react'
import { Link } from '@tanstack/react-router'
import type { ColDef, ICellRendererParams } from 'ag-grid-community'
import { UserPlus } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { can, useSession } from '@/lib/session'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { DataGrid } from '@/components/data-grid'
import { Page } from '@/components/layout/page'
import { AccountTypeBadge } from '@/components/person-badges'
import { usePeople, type Person } from './api'
import { UserSheet } from './user-sheet'

export default function UsersPage() {
  const { t } = useTranslation()
  const session = useSession()
  const [search, setSearch] = useState('')
  const [inactive, setInactive] = useState(false)
  const [openId, setOpenId] = useState<number | null>(null)
  const { data: people = [] } = usePeople(search, inactive)
  const open = people.find((p) => p.id === openId) ?? null

  const columns = useMemo<ColDef<Person>[]>(
    () => [
      { field: 'name', headerName: t('users.name'), flex: 1, minWidth: 160 },
      { field: 'email', headerName: t('users.email'), flex: 1, minWidth: 200 },
      {
        field: 'account_type',
        headerName: t('users.type'),
        width: 140,
        cellRenderer: (p: ICellRendererParams<Person>) =>
          p.data ? <AccountTypeBadge type={p.data.account_type} /> : null,
      },
      {
        field: 'sign_in_method',
        headerName: t('users.sign_in'),
        width: 110,
        valueFormatter: (p) => (p.value === 'entra' ? 'Microsoft' : 'Password'),
      },
      {
        headerName: t('users.roles'),
        flex: 1,
        valueGetter: (p) =>
          (p.data?.is_superuser ? ['Superuser'] : [])
            .concat(p.data?.roles?.map((r) => r.name) ?? [])
            .join(', '),
      },
      {
        headerName: t('users.teams'),
        flex: 1,
        valueGetter: (p) => p.data?.teams?.map((team) => team.name).join(', '),
      },
      {
        headerName: t('users.status'),
        width: 150,
        valueGetter: (p) =>
          !p.data?.active
            ? 'Deactivated'
            : !p.data?.activated
              ? 'Invitation pending'
              : 'Active',
        cellRenderer: (p: ICellRendererParams<Person>) => (
          <Badge
            variant={
              p.value === 'Active'
                ? 'secondary'
                : p.value === 'Deactivated'
                  ? 'destructive'
                  : 'outline'
            }
          >
            {p.value}
          </Badge>
        ),
      },
    ],
    [t]
  )

  return (
    <Page
      title={t('users.title')}
      description={t('users.description')}
      actions={
        can(session, 'portal.invite') ? (
          <Button size='sm' asChild>
            <Link to='/$' params={{ _splat: 'portal/users' }}>
              <UserPlus /> {t('users.invite')}
            </Link>
          </Button>
        ) : null
      }
    >
      <div className='flex flex-wrap items-center gap-4'>
        <Input
          className='h-8 w-80'
          placeholder={t('users.search')}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <div className='flex items-center gap-2'>
          <Switch
            id='inactive'
            checked={inactive}
            onCheckedChange={setInactive}
          />
          <Label htmlFor='inactive' className='text-sm font-normal'>
            {t('users.show_inactive')}
          </Label>
        </div>
      </div>
      <div className='h-[520px]'>
        <DataGrid
          rowData={people}
          columnDefs={columns}
          getRowId={(p) => String(p.data.id)}
          onRowClicked={(e) => e.data && setOpenId(e.data.id)}
          rowClass='cursor-pointer'
        />
      </div>
      <UserSheet person={open} onClose={() => setOpenId(null)} />
    </Page>
  )
}
