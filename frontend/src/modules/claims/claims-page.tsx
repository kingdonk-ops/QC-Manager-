import { useMemo, useState } from 'react'
import type { ColDef } from 'ag-grid-community'
import { Download, Plus, Sprout, Trash2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useCurrentProject } from '@/stores/use-current-project'
import { money } from '@/lib/format'
import { can, useSession } from '@/lib/session'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { DataGrid } from '@/components/data-grid'
import { Page } from '@/components/layout/page'
import { Field } from '@/components/records/fields'
import { StatusBadge } from '@/components/records/status-badge'
import {
  type Claim,
  exportUrl,
  type RateItem,
  useClaimActions,
  useClaims,
  useRateActions,
  useRateItems,
} from './api'
import { ClaimSheet } from './claim-sheet'

type Fmt = (v?: string | number | null) => string

function NewClaim({
  projectId,
  onCreated,
}: {
  projectId: number
  onCreated: (id: number) => void
}) {
  const { t } = useTranslation()
  const { create } = useClaimActions(projectId)
  const [d, setD] = useState({ start: '', end: '', pct: '5', cap: '' })
  return (
    <form
      className='flex flex-wrap items-end gap-2'
      onSubmit={(e) => {
        e.preventDefault()
        create.mutate(
          {
            period_start: d.start,
            period_end: d.end,
            retention_pct: d.pct || '0',
            retention_cap: d.cap || null,
          },
          { onSuccess: (c) => onCreated(c.id) }
        )
      }}
    >
      <Field label={t('claims.from')}>
        <Input
          className='h-8'
          type='date'
          value={d.start}
          onChange={(e) => setD({ ...d, start: e.target.value })}
          required
        />
      </Field>
      <Field label={t('claims.to')}>
        <Input
          className='h-8'
          type='date'
          value={d.end}
          onChange={(e) => setD({ ...d, end: e.target.value })}
          required
        />
      </Field>
      <Field label={t('claims.retention_pct')} className='w-28'>
        <Input
          className='h-8'
          type='number'
          step='any'
          min='0'
          max='100'
          value={d.pct}
          onChange={(e) => setD({ ...d, pct: e.target.value })}
        />
      </Field>
      <Field label={t('claims.retention_cap')} className='w-32'>
        <Input
          className='h-8'
          type='number'
          step='any'
          min='0'
          value={d.cap}
          onChange={(e) => setD({ ...d, cap: e.target.value })}
        />
      </Field>
      <Button size='sm' type='submit' disabled={create.isPending}>
        <Plus className='size-4' />
        {t('claims.new')}
      </Button>
    </form>
  )
}

function Register({ projectId, format }: { projectId: number; format: Fmt }) {
  const { t } = useTranslation()
  const session = useSession()
  const { data: claims = [] } = useClaims(projectId)
  const [openId, setOpenId] = useState<number | undefined>()
  const fmt = (p: { value?: unknown }) => format(p.value as string | null)
  const columns = useMemo<ColDef<Claim>[]>(
    () => [
      {
        field: 'code',
        headerName: t('claims.claim'),
        width: 100,
        cellClass: 'font-mono',
      },
      { field: 'period_start', headerName: t('claims.from'), width: 115 },
      { field: 'period_end', headerName: t('claims.to'), width: 115 },
      {
        field: 'status',
        headerName: t('claims.status'),
        width: 120,
        cellRenderer: (p: { value?: string }) => (
          <StatusBadge status={p.value} />
        ),
      },
      {
        headerName: t('claims.gross_to_date'),
        width: 140,
        type: 'rightAligned',
        valueGetter: (p) => p.data?.totals.gross_to_date,
        valueFormatter: fmt,
      },
      {
        headerName: t('claims.less_retention'),
        width: 120,
        type: 'rightAligned',
        valueGetter: (p) => p.data?.totals.retention_to_date,
        valueFormatter: fmt,
      },
      {
        headerName: t('claims.this_claim'),
        width: 140,
        type: 'rightAligned',
        valueGetter: (p) => p.data?.totals.this_claim,
        valueFormatter: fmt,
        cellClass: 'font-medium',
      },
      {
        field: 'certified_amount',
        headerName: t('claims.certified'),
        width: 130,
        type: 'rightAligned',
        valueFormatter: fmt,
      },
      {
        field: 'paid_amount',
        headerName: t('claims.paid'),
        width: 120,
        type: 'rightAligned',
        valueFormatter: fmt,
      },
    ],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [format, t]
  )
  return (
    <div className='flex flex-col gap-3'>
      <div className='flex flex-wrap items-end gap-2'>
        {can(session, 'claims.create') ? (
          <NewClaim projectId={projectId} onCreated={setOpenId} />
        ) : null}
        {can(session, 'claims.export') ? (
          <Button size='sm' variant='outline' className='ms-auto' asChild>
            <a href={exportUrl(projectId)}>
              <Download /> {t('claims.export')}
            </a>
          </Button>
        ) : null}
      </div>
      <div className='h-[480px]'>
        <DataGrid<Claim>
          rowData={claims}
          columnDefs={columns}
          getRowId={(p) => String(p.data.id)}
          onRowClicked={(e) => e.data && setOpenId(e.data.id)}
          rowClass='cursor-pointer'
        />
      </div>
      {openId ? (
        <ClaimSheet
          key={openId}
          projectId={projectId}
          id={openId}
          onClose={() => setOpenId(undefined)}
          format={format}
        />
      ) : null}
    </div>
  )
}

function Rates({ projectId, format }: { projectId: number; format: Fmt }) {
  const { t } = useTranslation()
  const session = useSession()
  const editable = can(session, 'claims.update')
  const { data: items = [] } = useRateItems(projectId)
  const { seed, create, update, remove } = useRateActions(projectId)
  const [d, setD] = useState({ code: '', description: '' })
  const fmt = (p: { value?: unknown }) => format(p.value as string | null)
  const columns = useMemo<ColDef<RateItem>[]>(
    () => [
      { field: 'code', headerName: t('claims.code'), width: 130, editable },
      {
        field: 'description',
        headerName: t('claims.description'),
        flex: 1,
        minWidth: 200,
        editable,
      },
      { field: 'node_path', headerName: t('claims.node'), width: 200 },
      { field: 'unit', headerName: t('claims.unit'), width: 80, editable },
      {
        field: 'contract_qty',
        headerName: t('claims.contract_qty'),
        width: 120,
        type: 'rightAligned',
        editable,
        valueFormatter: (p) => String(Number(p.value)),
      },
      {
        field: 'rate',
        headerName: t('claims.rate'),
        width: 110,
        type: 'rightAligned',
        editable,
        valueFormatter: fmt,
      },
      {
        field: 'contract_value',
        headerName: t('claims.contract_value'),
        width: 130,
        type: 'rightAligned',
        valueFormatter: fmt,
      },
      {
        headerName: '',
        width: 56,
        sortable: false,
        filter: false,
        cellRenderer: (p: { data?: RateItem }) =>
          editable && p.data ? (
            <Button
              size='icon'
              variant='ghost'
              className='size-7'
              aria-label={t('claims.delete')}
              onClick={() => remove.mutate(p.data!.id)}
            >
              <Trash2 className='size-4' />
            </Button>
          ) : null,
      },
    ],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [editable, format, t]
  )
  return (
    <div className='flex flex-col gap-3'>
      {editable ? (
        <div className='flex flex-wrap items-end gap-2'>
          <Button
            size='sm'
            variant='outline'
            disabled={seed.isPending}
            onClick={() => seed.mutate()}
          >
            <Sprout className='size-4' />
            {t('claims.seed')}
          </Button>
          <form
            className='flex flex-wrap items-end gap-2'
            onSubmit={(e) => {
              e.preventDefault()
              create.mutate(d, {
                onSuccess: () => setD({ code: '', description: '' }),
              })
            }}
          >
            <Input
              className='h-8 w-32'
              placeholder={t('claims.code')}
              value={d.code}
              onChange={(e) => setD({ ...d, code: e.target.value })}
              required
            />
            <Input
              className='h-8 w-64'
              placeholder={t('claims.description')}
              value={d.description}
              onChange={(e) => setD({ ...d, description: e.target.value })}
              required
            />
            <Button size='sm' type='submit'>
              <Plus className='size-4' />
              {t('claims.add_item')}
            </Button>
          </form>
        </div>
      ) : null}
      <p className='text-xs text-muted-foreground'>{t('claims.rates_hint')}</p>
      <div className='h-[480px]'>
        <DataGrid<RateItem>
          rowData={items}
          columnDefs={columns}
          getRowId={(p) => String(p.data.id)}
          onCellValueChanged={(e) => {
            const field = e.colDef.field
            if (!e.data || !field) return
            const value =
              e.newValue === '' || e.newValue === null
                ? null
                : String(e.newValue)
            update.mutate({ id: e.data.id, field, value })
          }}
        />
      </div>
    </div>
  )
}

export default function ClaimsPage() {
  const { t } = useTranslation()
  const project = useCurrentProject()
  const format = useMemo(() => {
    const f = money(project?.currency ?? 'AUD')
    return (v?: string | number | null) => f({ value: v })
  }, [project?.currency])
  return (
    <Page
      title={t('claims.title')}
      description={t('claims.description_page')}
      projectScoped
    >
      {project ? (
        <Tabs key={project.id} defaultValue='claims'>
          <TabsList>
            <TabsTrigger value='claims'>{t('claims.tab.claims')}</TabsTrigger>
            <TabsTrigger value='rates'>{t('claims.tab.rates')}</TabsTrigger>
          </TabsList>
          <TabsContent value='claims'>
            <Register projectId={project.id} format={format} />
          </TabsContent>
          <TabsContent value='rates'>
            <Rates projectId={project.id} format={format} />
          </TabsContent>
        </Tabs>
      ) : (
        <p className='text-sm text-muted-foreground'>
          {t('claims.no_project')}
        </p>
      )}
    </Page>
  )
}
