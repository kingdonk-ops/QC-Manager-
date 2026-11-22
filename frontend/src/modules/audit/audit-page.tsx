import { useMemo, useState } from 'react'
import type { ColDef } from 'ag-grid-community'
import { Download, ShieldCheck, ShieldAlert } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { can, useSession } from '@/lib/session'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { DataGrid } from '@/components/data-grid'
import { Page } from '@/components/layout/page'
import { UserSelect } from '@/components/native-select'
import {
  EMPTY,
  type Entry,
  type Filters,
  query,
  useEntries,
  useVerify,
} from './api'

function json(value: unknown) {
  return value === null || value === undefined ? '' : JSON.stringify(value)
}

export default function AuditPage() {
  const { t } = useTranslation()
  const session = useSession()
  const [filters, setFilters] = useState<Filters>(EMPTY)
  const [page, setPage] = useState(1)
  const { data } = useEntries(filters, page)
  const verify = useVerify()
  const rows = data?.data ?? []
  const total = data?.total_count ?? 0
  const set = (key: keyof Filters) => ({
    value: filters[key],
    onChange: (e: React.ChangeEvent<HTMLInputElement>) => {
      setPage(1)
      setFilters({ ...filters, [key]: e.target.value })
    },
  })

  const columns = useMemo<ColDef<Entry>[]>(
    () => [
      { field: 'seq', headerName: '#', width: 80, type: 'rightAligned' },
      {
        field: 'created_at',
        headerName: t('audit.when'),
        width: 170,
        valueFormatter: (p) =>
          p.value ? new Date(p.value as string).toLocaleString() : '',
      },
      { field: 'actor_name', headerName: t('audit.actor'), width: 150 },
      { field: 'action', headerName: t('audit.action'), width: 210 },
      {
        headerName: t('audit.entity'),
        width: 160,
        valueGetter: (p) =>
          p.data
            ? `${p.data.entity_type}${p.data.entity_id ? ` #${p.data.entity_id}` : ''}`
            : '',
      },
      {
        field: 'summary',
        headerName: t('audit.summary'),
        flex: 1,
        minWidth: 220,
      },
      {
        headerName: t('audit.change'),
        width: 260,
        valueGetter: (p) =>
          p.data
            ? [json(p.data.before), json(p.data.after)]
                .filter(Boolean)
                .join(' → ')
            : '',
        tooltipValueGetter: (p) => p.value as string,
      },
      {
        field: 'hash',
        headerName: t('audit.hash'),
        width: 130,
        cellClass: 'font-mono text-xs',
        valueFormatter: (p) => String(p.value ?? '').slice(0, 12),
      },
    ],
    [t]
  )

  const exportHref = (format: string) =>
    `/api/v1/audit/export?${new URLSearchParams({ ...query(filters), format })}`

  return (
    <Page
      title={t('audit.title')}
      description={t('audit.description')}
      actions={
        <>
          <Button
            size='sm'
            variant='outline'
            disabled={verify.isPending}
            onClick={() => verify.mutate()}
          >
            <ShieldCheck /> {t('audit.verify')}
          </Button>
          {can(session, 'audit.export') ? (
            <>
              <Button size='sm' variant='outline' asChild>
                <a href={exportHref('xlsx')}>
                  <Download /> Excel
                </a>
              </Button>
              <Button size='sm' variant='outline' asChild>
                <a href={exportHref('csv')}>
                  <Download /> CSV
                </a>
              </Button>
            </>
          ) : null}
        </>
      }
    >
      {verify.data ? (
        verify.data.ok ? (
          <Alert>
            <ShieldCheck />
            <AlertTitle>{t('audit.intact')}</AlertTitle>
            <AlertDescription>
              {t('audit.intact_detail', {
                count: verify.data.length,
                head: verify.data.head_hash.slice(0, 16),
              })}
            </AlertDescription>
          </Alert>
        ) : (
          <Alert variant='destructive'>
            <ShieldAlert />
            <AlertTitle>
              {t('audit.broken', { seq: verify.data.first_broken_seq })}
            </AlertTitle>
            <AlertDescription>{verify.data.problem}</AlertDescription>
          </Alert>
        )
      ) : null}
      <div className='flex flex-wrap items-center gap-2'>
        <Input
          className='h-8 w-44'
          placeholder={t('audit.entity_type')}
          aria-label={t('audit.entity_type')}
          {...set('entity_type')}
        />
        <Input
          className='h-8 w-28'
          placeholder={t('audit.entity_id')}
          aria-label={t('audit.entity_id')}
          {...set('entity_id')}
        />
        <Input
          className='h-8 w-44'
          placeholder={t('audit.action_prefix')}
          aria-label={t('audit.action_prefix')}
          {...set('action')}
        />
        <UserSelect
          className='h-8 w-44'
          placeholder={t('audit.any_actor')}
          value={filters.actor_id ? Number(filters.actor_id) : null}
          onChange={(id) => {
            setPage(1)
            setFilters({ ...filters, actor_id: id ? String(id) : '' })
          }}
        />
        <Input
          className='h-8 w-38'
          type='date'
          aria-label={t('audit.from')}
          {...set('date_from')}
        />
        <Input
          className='h-8 w-38'
          type='date'
          aria-label={t('audit.to')}
          {...set('date_to')}
        />
        <Input
          className='h-8 w-48'
          placeholder={t('audit.search')}
          aria-label={t('audit.search')}
          {...set('search')}
        />
      </div>
      <div className='h-[560px]'>
        <DataGrid<Entry>
          rowData={rows}
          columnDefs={columns}
          getRowId={(p) => String(p.data.seq)}
          tooltipShowDelay={300}
        />
      </div>
      <div className='flex items-center gap-2 text-sm text-muted-foreground'>
        {t('audit.count', { count: total })}
        <Button
          size='sm'
          variant='outline'
          className='ms-auto'
          disabled={page <= 1}
          onClick={() => setPage(page - 1)}
        >
          {t('audit.newer')}
        </Button>
        <Button
          size='sm'
          variant='outline'
          disabled={page * 50 >= total}
          onClick={() => setPage(page + 1)}
        >
          {t('audit.older')}
        </Button>
      </div>
    </Page>
  )
}
