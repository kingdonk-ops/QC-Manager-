import { useMemo, useState } from 'react'
import type { ColDef, ICellRendererParams } from 'ag-grid-community'
import { Copy, Plus, Trash2, Upload } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useCurrentProject } from '@/stores/use-current-project'
import { can, useSession } from '@/lib/session'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { ConfirmDialog } from '@/components/confirm-dialog'
import { DataGrid } from '@/components/data-grid'
import { Page } from '@/components/layout/page'
import {
  type Resource,
  type ResourceType,
  useResourceActions,
  useResources,
} from './api'
import { ImportDialog } from './import-dialog'
import { parseNumber } from './tree'

const RESOURCE_TYPES: ResourceType[] = [
  'material',
  'labour',
  'equipment',
  'subcontract',
]
const ALL = '__all__'
const PER_PAGE = 100

export default function ResourcesPage() {
  const { t } = useTranslation()
  const session = useSession()
  const project = useCurrentProject()
  const editable = can(session, 'boq.update')
  const [search, setSearch] = useState('')
  const [type, setType] = useState<ResourceType | null>(null)
  const [scope, setScope] = useState<'global' | 'project'>('global')
  const [page, setPage] = useState(1)
  const [importing, setImporting] = useState(false)
  const [deleting, setDeleting] = useState<Resource | null>(null)
  const [draft, setDraft] = useState({
    code: '',
    name: '',
    type: 'material' as ResourceType,
    unit: '',
    rate: '',
  })
  const projectId = scope === 'project' && project ? project.id : null
  const { data } = useResources({
    search,
    type,
    projectId,
    page,
    perPage: PER_PAGE,
  })
  const actions = useResourceActions()
  const currency = project?.currency ?? 'EUR'

  const columns = useMemo<ColDef<Resource>[]>(() => {
    const edit = (p: { data?: Resource }) =>
      editable && (!p.data?.project_id || p.data.project_id === projectId)
    return [
      {
        field: 'code',
        headerName: t('boq.col.code'),
        width: 120,
        editable: edit,
        cellClass: 'font-mono',
        pinned: 'left',
      },
      {
        field: 'name',
        headerName: t('boq.field.name'),
        flex: 1,
        minWidth: 240,
        editable: edit,
      },
      {
        field: 'type',
        headerName: t('boq.field.type'),
        width: 130,
        editable: edit,
        cellEditor: 'agSelectCellEditor',
        cellEditorParams: { values: RESOURCE_TYPES },
        valueFormatter: (p) => t(`boq.type.${p.value as string}`),
      },
      {
        field: 'trade',
        headerName: t('boq.field.trade'),
        width: 130,
        editable: edit,
      },
      {
        field: 'unit',
        headerName: t('boq.col.unit'),
        width: 80,
        editable: edit,
      },
      {
        field: 'rate',
        headerName: t('boq.field.rate'),
        width: 120,
        type: 'rightAligned',
        editable: edit,
        cellClass: 'tabular-nums',
        valueParser: (p) => parseNumber(String(p.newValue)) ?? p.oldValue,
        valueFormatter: (p) =>
          Number(p.value).toLocaleString(undefined, {
            minimumFractionDigits: 2,
            maximumFractionDigits: 4,
          }),
      },
      {
        field: 'currency',
        headerName: t('boq.field.currency'),
        width: 90,
        editable: edit,
      },
      { field: 'supplier_name', headerName: t('boq.res.supplier'), width: 160 },
      {
        field: 'notes',
        headerName: t('boq.field.notes'),
        width: 220,
        editable: edit,
        cellEditor: 'agLargeTextCellEditor',
        cellEditorPopup: true,
      },
      {
        headerName: '',
        width: 150,
        sortable: false,
        filter: false,
        cellRenderer: (p: ICellRendererParams<Resource>) => {
          const r = p.data
          if (!r) return null
          return (
            <div className='flex h-full items-center gap-2'>
              {r.base_id ? (
                <Badge variant='secondary'>{t('boq.res.overrides')}</Badge>
              ) : null}
              {editable && projectId && r.project_id === null ? (
                <button
                  type='button'
                  title={t('boq.res.override')}
                  aria-label={t('boq.res.override')}
                  className='text-muted-foreground hover:text-foreground'
                  onClick={() =>
                    actions.create.mutate({
                      code: r.code,
                      name: r.name,
                      type: r.type as ResourceType,
                      unit: r.unit,
                      rate: r.rate,
                      currency: r.currency,
                      trade: r.trade,
                      notes: r.notes,
                      project_id: projectId,
                      base_id: r.id,
                    })
                  }
                >
                  <Copy className='size-4' />
                </button>
              ) : null}
              {can(session, 'boq.delete') && edit(p) ? (
                <button
                  type='button'
                  aria-label={t('boq.delete')}
                  className='text-muted-foreground hover:text-red-600'
                  onClick={() => setDeleting(r)}
                >
                  <Trash2 className='size-4' />
                </button>
              ) : null}
            </div>
          )
        },
      },
    ]
  }, [actions.create, editable, projectId, session, t])

  const total = data?.total_count ?? 0

  return (
    <Page
      title={t('boq.res.title')}
      description={t('boq.res.description')}
      projectScoped
      actions={
        can(session, 'boq.import') ? (
          <Button
            size='sm'
            variant='outline'
            onClick={() => setImporting(true)}
          >
            <Upload /> {t('boq.res.import')}
          </Button>
        ) : null
      }
    >
      <div className='flex flex-wrap items-center gap-2'>
        <Input
          className='h-8 w-60'
          placeholder={t('boq.search')}
          value={search}
          onChange={(e) => {
            setSearch(e.target.value)
            setPage(1)
          }}
        />
        <Select
          value={type ?? ALL}
          onValueChange={(v) => {
            setType(v === ALL ? null : (v as ResourceType))
            setPage(1)
          }}
        >
          <SelectTrigger size='sm' className='w-40'>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>{t('boq.res.all_types')}</SelectItem>
            {RESOURCE_TYPES.map((r) => (
              <SelectItem key={r} value={r}>
                {t(`boq.type.${r}`)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {project ? (
          <Select
            value={scope}
            onValueChange={(v) => setScope(v as 'global' | 'project')}
          >
            <SelectTrigger size='sm' className='w-56'>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value='global'>
                {t('boq.res.scope_global')}
              </SelectItem>
              <SelectItem value='project'>
                {t('boq.res.scope_project')} ({project.code})
              </SelectItem>
            </SelectContent>
          </Select>
        ) : null}
      </div>

      {editable ? (
        <form
          className='flex flex-wrap items-center gap-2'
          onSubmit={(e) => {
            e.preventDefault()
            actions.create.mutate(
              {
                ...draft,
                rate: parseNumber(draft.rate) ?? '0',
                currency,
                project_id: projectId,
              },
              {
                onSuccess: () =>
                  setDraft({ ...draft, code: '', name: '', rate: '' }),
              }
            )
          }}
        >
          <Input
            className='h-8 w-28 font-mono'
            placeholder={t('boq.col.code')}
            value={draft.code}
            required
            maxLength={40}
            onChange={(e) => setDraft({ ...draft, code: e.target.value })}
          />
          <Input
            className='h-8 w-64'
            placeholder={t('boq.field.name')}
            value={draft.name}
            required
            maxLength={300}
            onChange={(e) => setDraft({ ...draft, name: e.target.value })}
          />
          <Select
            value={draft.type}
            onValueChange={(v) =>
              setDraft({ ...draft, type: v as ResourceType })
            }
          >
            <SelectTrigger size='sm' className='w-36'>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {RESOURCE_TYPES.map((r) => (
                <SelectItem key={r} value={r}>
                  {t(`boq.type.${r}`)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Input
            className='h-8 w-20'
            placeholder={t('boq.col.unit')}
            value={draft.unit}
            maxLength={20}
            onChange={(e) => setDraft({ ...draft, unit: e.target.value })}
          />
          <Input
            className='h-8 w-28 text-end'
            placeholder={t('boq.field.rate')}
            value={draft.rate}
            onChange={(e) => setDraft({ ...draft, rate: e.target.value })}
          />
          <Button size='sm' type='submit' disabled={actions.create.isPending}>
            <Plus /> {t('boq.res.add')}
          </Button>
        </form>
      ) : null}

      <div className='min-h-[420px] flex-1'>
        <DataGrid<Resource>
          rowData={data?.data ?? []}
          columnDefs={columns}
          getRowId={(p) => String(p.data.id)}
          onCellValueChanged={(e) => {
            if (!e.data || !e.colDef.field || e.newValue === e.oldValue) return
            actions.update.mutate({
              id: e.data.id,
              [e.colDef.field]: e.newValue,
            })
          }}
        />
      </div>
      {total > PER_PAGE ? (
        <div className='flex items-center justify-end gap-2 text-sm'>
          <Button
            size='sm'
            variant='outline'
            disabled={page <= 1}
            onClick={() => setPage(page - 1)}
          >
            ‹
          </Button>
          <span className='tabular-nums'>
            {page} / {Math.ceil(total / PER_PAGE)}
          </span>
          <Button
            size='sm'
            variant='outline'
            disabled={page * PER_PAGE >= total}
            onClick={() => setPage(page + 1)}
          >
            ›
          </Button>
        </div>
      ) : null}

      <ImportDialog
        open={importing}
        onOpenChange={setImporting}
        title={t('boq.res.import')}
        previewUrl='/api/v1/boq/resources/import/preview'
        importUrl='/api/v1/boq/resources/import'
        fields={{
          currency,
          ...(projectId ? { project_id: String(projectId) } : {}),
        }}
        onDone={actions.refresh}
      />
      <ConfirmDialog
        open={deleting !== null}
        onOpenChange={(o) => !o && setDeleting(null)}
        title={t('boq.res.delete')}
        desc={t('boq.res.delete_desc')}
        destructive
        confirmText={t('boq.delete')}
        handleConfirm={() => {
          if (deleting) actions.remove.mutate(deleting.id)
          setDeleting(null)
        }}
      />
    </Page>
  )
}
