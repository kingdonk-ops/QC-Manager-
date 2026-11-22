import { useMemo, useState } from 'react'
import type { ColDef, ICellRendererParams } from 'ag-grid-community'
import { Download, Plus } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useCurrentProject } from '@/stores/use-current-project'
import { can, useSession } from '@/lib/session'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { DataGrid } from '@/components/data-grid'
import { Page } from '@/components/layout/page'
import { NativeSelect, UserSelect } from '@/components/native-select'
import { StatusBadge } from '@/components/records/status-badge'
import {
  type Filters,
  LIFECYCLE,
  type Ncr,
  SEVERITIES,
  SOURCES,
  useCreateNcr,
  useNcrs,
} from './api'
import { NcrSheet } from './ncr-sheet'

function initialId() {
  const id = Number(new URLSearchParams(window.location.search).get('id'))
  return Number.isFinite(id) && id > 0 ? id : null
}

function NewNcr({
  projectId,
  onClose,
  onCreated,
}: {
  projectId: number
  onClose: () => void
  onCreated: (id: number) => void
}) {
  const { t } = useTranslation()
  const create = useCreateNcr()
  const [draft, setDraft] = useState({
    title: '',
    description: '',
    location: '',
    trade: '',
    severity: 'minor',
    source: 'other',
    spec_reference: '',
    responsible_user_id: null as number | null,
  })
  const text = (key: keyof typeof draft) => ({
    value: (draft[key] as string) ?? '',
    onChange: (
      e: React.ChangeEvent<
        HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement
      >
    ) => setDraft({ ...draft, [key]: e.target.value }),
  })
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className='sm:max-w-lg'>
        <DialogHeader>
          <DialogTitle>{t('ncr.new')}</DialogTitle>
        </DialogHeader>
        <form
          id='new-ncr'
          className='grid gap-3'
          onSubmit={(e) => {
            e.preventDefault()
            create.mutate(
              {
                project_id: projectId,
                title: draft.title,
                description: draft.description || null,
                location: draft.location || null,
                trade: draft.trade || null,
                severity: draft.severity as never,
                source: draft.source as never,
                spec_reference: draft.spec_reference || null,
                responsible_user_id: draft.responsible_user_id,
              },
              {
                onSuccess: (made) => {
                  onClose()
                  onCreated(made.id)
                },
              }
            )
          }}
        >
          <div className='grid gap-1.5'>
            <Label htmlFor='new-ncr-title'>{t('ncr.title_field')}</Label>
            <Input id='new-ncr-title' required {...text('title')} />
          </div>
          <div className='grid gap-1.5'>
            <Label htmlFor='new-ncr-desc'>{t('ncr.description_field')}</Label>
            <Textarea id='new-ncr-desc' {...text('description')} />
          </div>
          <div className='grid grid-cols-2 gap-3'>
            <div className='grid gap-1.5'>
              <Label htmlFor='new-ncr-sev'>{t('ncr.severity')}</Label>
              <NativeSelect
                id='new-ncr-sev'
                values={SEVERITIES}
                {...text('severity')}
              />
            </div>
            <div className='grid gap-1.5'>
              <Label htmlFor='new-ncr-src'>{t('ncr.source')}</Label>
              <NativeSelect
                id='new-ncr-src'
                values={SOURCES}
                {...text('source')}
              />
            </div>
            <div className='grid gap-1.5'>
              <Label htmlFor='new-ncr-loc'>{t('ncr.location')}</Label>
              <Input id='new-ncr-loc' {...text('location')} />
            </div>
            <div className='grid gap-1.5'>
              <Label htmlFor='new-ncr-trade'>{t('ncr.trade')}</Label>
              <Input id='new-ncr-trade' {...text('trade')} />
            </div>
            <div className='grid gap-1.5'>
              <Label htmlFor='new-ncr-spec'>{t('ncr.spec_reference')}</Label>
              <Input id='new-ncr-spec' {...text('spec_reference')} />
            </div>
            <div className='grid gap-1.5'>
              <Label>{t('ncr.responsible_user')}</Label>
              <UserSelect
                value={draft.responsible_user_id}
                onChange={(id) =>
                  setDraft({ ...draft, responsible_user_id: id })
                }
              />
            </div>
          </div>
        </form>
        <DialogFooter>
          <Button type='submit' form='new-ncr' disabled={create.isPending}>
            {t('ncr.raise')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function Register({ projectId }: { projectId: number }) {
  const { t } = useTranslation()
  const session = useSession()
  const [filters, setFilters] = useState<Filters>({
    status: '',
    severity: '',
    search: '',
  })
  const [openId, setOpenId] = useState<number | null>(initialId)
  const [creating, setCreating] = useState(false)
  const { data: rows = [] } = useNcrs(projectId, filters)

  const columns = useMemo<ColDef<Ncr>[]>(
    () => [
      {
        field: 'code',
        headerName: t('ncr.code'),
        width: 100,
        cellClass: 'font-mono',
      },
      {
        field: 'title',
        headerName: t('ncr.title_field'),
        flex: 1,
        minWidth: 220,
      },
      {
        field: 'severity',
        headerName: t('ncr.severity'),
        width: 110,
        cellRenderer: (p: ICellRendererParams<Ncr>) => (
          <StatusBadge status={p.value} />
        ),
      },
      {
        field: 'status',
        headerName: t('ncr.status'),
        width: 210,
        cellRenderer: (p: ICellRendererParams<Ncr>) => (
          <StatusBadge status={p.value} />
        ),
      },
      { field: 'source', headerName: t('ncr.source'), width: 110 },
      { field: 'location', headerName: t('ncr.location'), width: 140 },
      { field: 'trade', headerName: t('ncr.trade'), width: 120 },
      {
        headerName: t('ncr.responsible'),
        width: 160,
        valueGetter: (p) =>
          p.data?.responsible_user_name ??
          p.data?.responsible_contact_name ??
          p.data?.responsible_company_name,
      },
      { field: 'raised_on', headerName: t('ncr.raised_on'), width: 110 },
      {
        field: 'open_actions',
        headerName: t('ncr.open_actions'),
        width: 110,
        type: 'rightAligned',
      },
      {
        field: 'total_cost',
        headerName: t('ncr.total_cost'),
        width: 120,
        type: 'rightAligned',
        valueFormatter: (p) =>
          Number(p.value ?? 0).toLocaleString(undefined, {
            maximumFractionDigits: 0,
          }),
      },
    ],
    [t]
  )

  return (
    <>
      <div className='flex flex-wrap items-center gap-2'>
        <Input
          className='h-8 w-60'
          placeholder={t('ncr.search')}
          value={filters.search}
          onChange={(e) => setFilters({ ...filters, search: e.target.value })}
        />
        <NativeSelect
          className='h-8 w-56'
          aria-label={t('ncr.status')}
          placeholder={t('ncr.all_statuses')}
          values={LIFECYCLE}
          value={filters.status}
          onChange={(e) => setFilters({ ...filters, status: e.target.value })}
        />
        <NativeSelect
          className='h-8 w-40'
          aria-label={t('ncr.severity')}
          placeholder={t('ncr.all_severities')}
          values={SEVERITIES}
          value={filters.severity}
          onChange={(e) => setFilters({ ...filters, severity: e.target.value })}
        />
        <div className='ms-auto flex gap-2'>
          {can(session, 'ncr.export') ? (
            <Button size='sm' variant='outline' asChild>
              <a
                href={`/api/v1/ncr/export?project_id=${projectId}&format=xlsx`}
              >
                <Download /> {t('ncr.export')}
              </a>
            </Button>
          ) : null}
          {can(session, 'ncr.create') ? (
            <Button size='sm' onClick={() => setCreating(true)}>
              <Plus /> {t('ncr.new')}
            </Button>
          ) : null}
        </div>
      </div>
      <div className='h-[560px]'>
        <DataGrid<Ncr>
          rowData={rows}
          columnDefs={columns}
          getRowId={(p) => String(p.data.id)}
          rowClass='cursor-pointer'
          onRowClicked={(e) => e.data && setOpenId(e.data.id)}
        />
      </div>
      {creating ? (
        <NewNcr
          projectId={projectId}
          onClose={() => setCreating(false)}
          onCreated={setOpenId}
        />
      ) : null}
      <NcrSheet id={openId} onClose={() => setOpenId(null)} />
    </>
  )
}

export default function NcrPage() {
  const { t } = useTranslation()
  const project = useCurrentProject()
  return (
    <Page
      title={t('ncr.page_title')}
      description={t('ncr.description')}
      projectScoped
    >
      {project ? (
        <Register key={project.id} projectId={project.id} />
      ) : (
        <p className='text-sm text-muted-foreground'>{t('ncr.no_project')}</p>
      )}
    </Page>
  )
}
