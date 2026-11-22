import { useMemo, useState } from 'react'
import type { ColDef, ICellRendererParams } from 'ag-grid-community'
import { FileSpreadsheet, ListPlus, Plus, Trash2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { api, unwrap } from '@/api/client'
import { useCurrentProject } from '@/stores/use-current-project'
import { money } from '@/lib/format'
import { handleServerError } from '@/lib/handle-server-error'
import { can, useSession } from '@/lib/session'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Textarea } from '@/components/ui/textarea'
import { DataGrid } from '@/components/data-grid'
import { Page } from '@/components/layout/page'
import { StatusBadge } from '@/components/records/status-badge'
import {
  STATUSES,
  useComponents,
  useRefresh,
  useSpaces,
  useSystems,
  useTypes,
  useWrite,
  type AssetType,
  type Component,
  type Place,
} from './api'
import { CobiePanel } from './cobie-panel'
import { ImportWizard } from './import-wizard'
import { ComponentSheet, TypeSheet } from './sheets'
import { SpatialTree } from './spatial-tree'

const NONE = '—'

function placeSpace(place: Place) {
  return place.kind === 'space' ? place.id : undefined
}

function ComponentsGrid({
  projectId,
  place,
  onOpen,
}: {
  projectId: number
  place: Place
  onOpen: (c: Component) => void
}) {
  const session = useSession()
  const { data: rows = [] } = useComponents(projectId, place)
  const { data: types = [] } = useTypes(projectId)
  const { data: spaces = [] } = useSpaces(projectId)
  const write = useWrite(projectId)
  const editable = can(session, 'assets.update')
  const columns = useMemo<ColDef<Component>[]>(
    () => [
      {
        field: 'name',
        headerName: 'Name / tag',
        editable,
        pinned: 'left',
        width: 160,
      },
      {
        field: 'type_name',
        headerName: 'Type',
        editable,
        width: 170,
        cellEditor: 'agSelectCellEditor',
        cellEditorParams: { values: [NONE, ...types.map((t) => t.name)] },
      },
      {
        field: 'space_name',
        headerName: 'Space',
        editable,
        width: 170,
        cellEditor: 'agSelectCellEditor',
        cellEditorParams: { values: [NONE, ...spaces.map((s) => s.name)] },
      },
      { field: 'floor_name', headerName: 'Floor', width: 110 },
      {
        field: 'status',
        headerName: 'Status',
        editable,
        width: 140,
        cellEditor: 'agSelectCellEditor',
        cellEditorParams: { values: [...STATUSES] },
        cellRenderer: (p: ICellRendererParams<Component>) => (
          <StatusBadge status={p.value} />
        ),
      },
      { field: 'serial_number', headerName: 'Serial', editable, width: 130 },
      {
        field: 'asset_identifier',
        headerName: 'Asset ID',
        editable,
        width: 120,
      },
      { field: 'bar_code', headerName: 'Barcode', editable, width: 120 },
      {
        field: 'installation_date',
        headerName: 'Installed',
        editable,
        width: 120,
      },
      {
        field: 'warranty_start_date',
        headerName: 'Warranty start',
        editable,
        width: 130,
      },
      {
        field: 'document_count',
        headerName: 'Docs',
        width: 80,
        type: 'rightAligned',
      },
    ],
    [editable, types, spaces]
  )
  return (
    <div className='h-[560px]'>
      <DataGrid
        rowData={rows}
        columnDefs={columns}
        getRowId={(p) => String(p.data.id)}
        singleClickEdit
        onCellValueChanged={(e) => {
          const field = e.colDef.field
          if (!e.data || !field) return
          let body: Record<string, unknown>
          if (field === 'type_name')
            body = {
              type_id: types.find((t) => t.name === e.newValue)?.id ?? null,
            }
          else if (field === 'space_name')
            body = {
              space_id: spaces.find((s) => s.name === e.newValue)?.id ?? null,
            }
          else body = { [field]: e.newValue === '' ? null : e.newValue }
          write.mutate({ kind: 'components', id: e.data.id, body })
        }}
        onRowDoubleClicked={(e) => e.data && onOpen(e.data)}
        overlayNoRowsTemplate='No components here yet. Add them one by one, as a list of tags, or import a spreadsheet.'
      />
    </div>
  )
}

function TypesGrid({
  projectId,
  currency,
  onOpen,
}: {
  projectId: number
  currency: string
  onOpen: (t: AssetType) => void
}) {
  const session = useSession()
  const { data: rows = [] } = useTypes(projectId)
  const write = useWrite(projectId)
  const editable = can(session, 'assets.update')
  const numeric = new Set([
    'warranty_duration_parts',
    'warranty_duration_labor',
    'expected_life',
  ])
  const columns = useMemo<ColDef<AssetType>[]>(
    () => [
      {
        field: 'name',
        headerName: 'Name',
        editable,
        pinned: 'left',
        width: 180,
      },
      {
        field: 'category',
        headerName: 'Category',
        editable,
        flex: 1,
        minWidth: 180,
      },
      { field: 'manufacturer_name', headerName: 'Manufacturer', width: 180 },
      { field: 'model_number', headerName: 'Model', editable, width: 130 },
      {
        field: 'warranty_duration_parts',
        headerName: 'Warranty (y)',
        editable,
        width: 120,
        type: 'rightAligned',
      },
      {
        field: 'expected_life',
        headerName: 'Life (y)',
        editable,
        width: 100,
        type: 'rightAligned',
      },
      {
        field: 'replacement_cost',
        headerName: 'Replacement cost',
        editable,
        width: 150,
        type: 'rightAligned',
        valueFormatter: money(currency),
      },
      {
        field: 'component_count',
        headerName: 'Components',
        width: 120,
        type: 'rightAligned',
      },
    ],
    [editable, currency]
  )
  return (
    <div className='h-[560px]'>
      <DataGrid
        rowData={rows}
        columnDefs={columns}
        getRowId={(p) => String(p.data.id)}
        singleClickEdit
        onCellValueChanged={(e) => {
          const field = e.colDef.field
          if (!e.data || !field) return
          const raw =
            e.newValue === '' || e.newValue === undefined ? null : e.newValue
          const value =
            raw !== null && numeric.has(field)
              ? Number(raw)
              : raw !== null && field === 'replacement_cost'
                ? String(raw)
                : raw
          write.mutate({
            kind: 'types',
            id: e.data.id,
            body: { [field]: value },
          })
        }}
        onRowDoubleClicked={(e) => e.data && onOpen(e.data)}
        overlayNoRowsTemplate='No product types yet.'
      />
    </div>
  )
}

function SystemsTab({ projectId }: { projectId: number }) {
  const session = useSession()
  const { data: systems = [] } = useSystems(projectId)
  const { data: components = [] } = useComponents(projectId, { kind: 'all' })
  const write = useWrite(projectId)
  const [selected, setSelected] = useState<number | null>(null)
  const [filter, setFilter] = useState('')
  const editable = can(session, 'assets.update')
  const system = systems.find((s) => s.id === (selected ?? systems[0]?.id))
  const members = new Set(system?.component_ids ?? [])
  const shown = components.filter((c) =>
    c.name.toLowerCase().includes(filter.toLowerCase())
  )
  return (
    <div className='flex min-h-[420px] gap-3'>
      <div className='grid w-72 shrink-0 content-start gap-1'>
        {systems.map((s) => (
          <div
            key={s.id}
            className={`group flex items-center gap-2 rounded-md border px-2 py-1.5 text-sm ${system?.id === s.id ? 'border-primary' : ''}`}
          >
            <button
              className='min-w-0 flex-1 text-start'
              onClick={() => setSelected(s.id)}
            >
              <span className='block truncate font-medium'>{s.name}</span>
              <span className='block text-xs text-muted-foreground'>
                {s.category ?? 'No category'} · {s.component_ids?.length ?? 0}{' '}
                components
              </span>
            </button>
            {can(session, 'assets.delete') ? (
              <button
                aria-label={`Delete ${s.name}`}
                className='invisible group-hover:visible'
                onClick={() =>
                  window.confirm(`Delete the system ${s.name}?`) &&
                  write.mutate({ kind: 'systems', id: s.id, remove: true })
                }
              >
                <Trash2 className='size-3.5 text-muted-foreground' />
              </button>
            ) : null}
          </div>
        ))}
        {!systems.length ? (
          <p className='text-sm text-muted-foreground'>No systems yet.</p>
        ) : null}
      </div>
      {system ? (
        <div className='grid flex-1 content-start gap-2'>
          <div className='flex items-center gap-2'>
            <h3 className='font-medium'>{system.name}: components</h3>
            <Input
              className='ms-auto h-8 w-56'
              placeholder='Filter components'
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
            />
          </div>
          <div className='grid max-h-[480px] grid-cols-2 gap-1 overflow-y-auto lg:grid-cols-3'>
            {shown.map((c) => (
              <label key={c.id} className='flex items-center gap-2 text-sm'>
                <Checkbox
                  disabled={!editable}
                  checked={members.has(c.id)}
                  onCheckedChange={(on) =>
                    write.mutate({
                      kind: 'systems',
                      id: system.id,
                      body: {
                        component_ids: on
                          ? [...members, c.id]
                          : [...members].filter((id) => id !== c.id),
                      },
                    })
                  }
                />
                <span className='truncate'>{c.name}</span>
                <span className='truncate text-xs text-muted-foreground'>
                  {c.type_name}
                </span>
              </label>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  )
}

function NewDialog({
  projectId,
  open,
  onClose,
  kind,
  place,
}: {
  projectId: number
  open: boolean
  onClose: () => void
  kind: 'component' | 'bulk' | 'type' | 'system'
  place: Place
}) {
  const write = useWrite(projectId)
  const refresh = useRefresh(projectId)
  const [name, setName] = useState('')
  const [category, setCategory] = useState('')
  const [names, setNames] = useState('')
  const [pending, setPending] = useState(false)
  const close = () => {
    setName('')
    setCategory('')
    setNames('')
    onClose()
  }
  const save = async () => {
    setPending(true)
    try {
      if (kind === 'bulk') {
        const list = names
          .split(/[\n,;]+/)
          .map((n) => n.trim())
          .filter(Boolean)
        const result = await unwrap(
          api.POST('/api/v1/assets/{project_id}/components/bulk', {
            params: { path: { project_id: projectId } },
            body: {
              names: list,
              space_id: placeSpace(place) ?? null,
              status: 'planned',
            },
          })
        )
        toast.success(
          `${result.created.length} added` +
            (result.skipped?.length
              ? `, ${result.skipped.length} already there`
              : '')
        )
        refresh()
      } else {
        const body: Record<string, unknown> = { name: name.trim() }
        if (kind !== 'component' && category.trim())
          body.category = category.trim()
        if (kind === 'component' && placeSpace(place))
          body.space_id = placeSpace(place)
        await write.mutateAsync({
          kind:
            kind === 'type'
              ? 'types'
              : kind === 'system'
                ? 'systems'
                : 'components',
          body,
        })
      }
      close()
    } catch (error) {
      if (kind === 'bulk') handleServerError(error)
    } finally {
      setPending(false)
    }
  }
  const titles = {
    component: 'Add a component',
    bulk: 'Add components from a list of tags',
    type: 'Add a product type',
    system: 'Add a system',
  }
  return (
    <Dialog open={open} onOpenChange={(o) => !o && close()}>
      <DialogContent className='sm:max-w-md'>
        <DialogHeader>
          <DialogTitle>{titles[kind]}</DialogTitle>
          {kind === 'bulk' || kind === 'component' ? (
            <DialogDescription>
              {placeSpace(place)
                ? 'They go in the space picked on the left.'
                : 'Pick a space on the left first to place them there.'}
            </DialogDescription>
          ) : null}
        </DialogHeader>
        {kind === 'bulk' ? (
          <Textarea
            autoFocus
            rows={8}
            aria-label='Tags'
            placeholder={'AHU-01\nAHU-02\nFCU-L2-01'}
            value={names}
            onChange={(e) => setNames(e.target.value)}
          />
        ) : (
          <div className='grid gap-3'>
            <div className='grid gap-1'>
              <Label htmlFor='new-name'>Name</Label>
              <Input
                id='new-name'
                autoFocus
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </div>
            {kind !== 'component' ? (
              <div className='grid gap-1'>
                <Label htmlFor='new-category'>Category</Label>
                <Input
                  id='new-category'
                  placeholder={
                    kind === 'type'
                      ? 'e.g. Pr_65_53_67 : Centrifugal pumps'
                      : 'e.g. Chilled water'
                  }
                  value={category}
                  onChange={(e) => setCategory(e.target.value)}
                />
              </div>
            ) : null}
          </div>
        )}
        <DialogFooter>
          <Button variant='outline' onClick={close}>
            Cancel
          </Button>
          <Button
            disabled={
              pending || (kind === 'bulk' ? !names.trim() : !name.trim())
            }
            onClick={() => void save()}
          >
            Add
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function Register({
  projectId,
  currency,
}: {
  projectId: number
  currency: string
}) {
  const session = useSession()
  const [place, setPlace] = useState<Place>({ kind: 'all' })
  const [tab, setTab] = useState('components')
  const [openComponent, setOpenComponent] = useState<number | null>(null)
  const [openType, setOpenType] = useState<number | null>(null)
  const [adding, setAdding] = useState<
    'component' | 'bulk' | 'type' | 'system' | null
  >(null)
  const [importing, setImporting] = useState(false)
  const { data: components = [] } = useComponents(projectId, place)
  const { data: types = [] } = useTypes(projectId)
  const canCreate = can(session, 'assets.create')

  return (
    <div className='flex min-h-0 flex-1 gap-3'>
      <SpatialTree projectId={projectId} place={place} onPlace={setPlace} />
      <Tabs value={tab} onValueChange={setTab} className='min-w-0 flex-1'>
        <div className='flex flex-wrap items-center gap-2'>
          <TabsList>
            <TabsTrigger value='components'>Components</TabsTrigger>
            <TabsTrigger value='types'>Types</TabsTrigger>
            <TabsTrigger value='systems'>Systems</TabsTrigger>
            <TabsTrigger value='cobie'>COBie</TabsTrigger>
          </TabsList>
          <div className='ms-auto flex gap-2'>
            {can(session, 'assets.import') ? (
              <Button
                size='sm'
                variant='outline'
                onClick={() => setImporting(true)}
              >
                <FileSpreadsheet /> Import
              </Button>
            ) : null}
            {canCreate && tab === 'components' ? (
              <>
                <Button
                  size='sm'
                  variant='outline'
                  onClick={() => setAdding('bulk')}
                >
                  <ListPlus /> Add list
                </Button>
                <Button size='sm' onClick={() => setAdding('component')}>
                  <Plus /> Component
                </Button>
              </>
            ) : null}
            {canCreate && tab === 'types' ? (
              <Button size='sm' onClick={() => setAdding('type')}>
                <Plus /> Type
              </Button>
            ) : null}
            {canCreate && tab === 'systems' ? (
              <Button size='sm' onClick={() => setAdding('system')}>
                <Plus /> System
              </Button>
            ) : null}
          </div>
        </div>
        <TabsContent value='components'>
          <ComponentsGrid
            projectId={projectId}
            place={place}
            onOpen={(c) => setOpenComponent(c.id)}
          />
        </TabsContent>
        <TabsContent value='types'>
          <TypesGrid
            projectId={projectId}
            currency={currency}
            onOpen={(t) => setOpenType(t.id)}
          />
        </TabsContent>
        <TabsContent value='systems'>
          <SystemsTab projectId={projectId} />
        </TabsContent>
        <TabsContent value='cobie'>
          <CobiePanel projectId={projectId} />
        </TabsContent>
      </Tabs>
      <ComponentSheet
        projectId={projectId}
        component={components.find((c) => c.id === openComponent) ?? null}
        onClose={() => setOpenComponent(null)}
      />
      <TypeSheet
        projectId={projectId}
        type={types.find((t) => t.id === openType) ?? null}
        onClose={() => setOpenType(null)}
      />
      {adding ? (
        <NewDialog
          projectId={projectId}
          open
          kind={adding}
          place={place}
          onClose={() => setAdding(null)}
        />
      ) : null}
      <ImportWizard
        projectId={projectId}
        open={importing}
        onClose={() => setImporting(false)}
      />
    </div>
  )
}

export default function AssetsPage() {
  const { t } = useTranslation()
  const project = useCurrentProject()
  return (
    <Page
      title={t('assets.title')}
      description={t('assets.description')}
      projectScoped
      fixed
    >
      {project ? (
        <Register
          key={project.id}
          projectId={project.id}
          currency={project.currency}
        />
      ) : (
        <p className='text-sm text-muted-foreground'>Choose a project.</p>
      )}
    </Page>
  )
}
