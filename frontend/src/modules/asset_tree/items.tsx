import { useMemo, useState } from 'react'
import type { ColDef } from 'ag-grid-community'
import { Plus, Trash2 } from 'lucide-react'
import { api, unwrap } from '@/api/client'
import { can, useSession } from '@/lib/session'
import { useSavedViews } from '@/hooks/use-saved-views'
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
import { NativeSelect } from '@/components/native-select'
import { RecordSheet } from '@/components/records/record-sheet'
import { StatusBadge } from '@/components/records/status-badge'
import { SavedViewsMenu } from '@/components/saved-views'
import {
  IDENTIFIER_KINDS,
  type Item,
  type ItemType,
  type TreeNode,
  schemaFields,
  useItem,
  useItemTypes,
  useItems,
  useTreeWrite,
} from './api'
import { SchemaFieldsEditor } from './pickers'
import type { TermFn } from './terminology'

function NewItem({
  projectId,
  node,
  types,
  term,
  onClose,
  onCreated,
}: {
  projectId: number
  node: TreeNode
  types: ItemType[]
  term: TermFn
  onClose: () => void
  onCreated: (id: number) => void
}) {
  const [typeKey, setTypeKey] = useState(types[0]?.key ?? '')
  const [tag, setTag] = useState('')
  const create = useTreeWrite(projectId, () =>
    unwrap(
      api.POST('/api/v1/asset-tree/items/', {
        body: {
          project_id: projectId,
          node_id: node.id,
          item_type_key: typeKey,
          tag: tag.trim(),
        },
      })
    )
  )
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className='sm:max-w-md'>
        <DialogHeader>
          <DialogTitle>
            New {term('noun.item').toLowerCase()} on {node.display_path}
          </DialogTitle>
        </DialogHeader>
        <form
          id='new-item'
          className='grid gap-3'
          onSubmit={(e) => {
            e.preventDefault()
            create.mutate(undefined, {
              onSuccess: (item) => {
                onCreated((item as Item).id)
                onClose()
              },
            })
          }}
        >
          <div className='grid gap-1.5'>
            <Label htmlFor='item-type'>{term('noun.item_type')}</Label>
            <NativeSelect
              id='item-type'
              options={types.map((t) => ({ value: t.key, label: t.name }))}
              value={typeKey}
              onChange={(e) => setTypeKey(e.target.value)}
            />
          </div>
          <div className='grid gap-1.5'>
            <Label htmlFor='item-tag'>Tag</Label>
            <Input
              id='item-tag'
              required
              value={tag}
              onChange={(e) => setTag(e.target.value)}
            />
          </div>
        </form>
        <DialogFooter>
          <Button
            type='submit'
            form='new-item'
            disabled={!tag.trim() || !typeKey || create.isPending}
          >
            Create
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function Identifiers({ projectId, item }: { projectId: number; item: Item }) {
  const session = useSession()
  const editable = can(session, 'asset_tree.update')
  const [kind, setKind] = useState<string>('barcode')
  const [value, setValue] = useState('')
  const add = useTreeWrite(projectId, () =>
    unwrap(
      api.POST('/api/v1/asset-tree/items/{item_id}/identifiers', {
        params: { path: { item_id: item.id } },
        body: { kind: kind as 'barcode', value: value.trim() },
      })
    )
  )
  const deactivate = useTreeWrite(projectId, (identifierId: number) =>
    unwrap(
      api.DELETE(
        '/api/v1/asset-tree/items/{item_id}/identifiers/{identifier_id}',
        {
          params: { path: { item_id: item.id, identifier_id: identifierId } },
        }
      )
    )
  )
  return (
    <div className='grid gap-3'>
      <ul className='grid gap-1 text-sm'>
        {item.identifiers?.map((i) => (
          <li
            key={i.id}
            className='flex items-center gap-2 rounded-md border px-2 py-1'
          >
            <span className='w-16 text-xs text-muted-foreground uppercase'>
              {i.kind}
            </span>
            <span
              className={
                i.is_active
                  ? 'font-mono'
                  : 'font-mono text-muted-foreground line-through'
              }
            >
              {i.value}
            </span>
            {i.is_active && editable ? (
              <Button
                size='icon'
                variant='ghost'
                className='ms-auto size-7'
                aria-label={`Deactivate ${i.value}`}
                onClick={() => deactivate.mutate(i.id)}
              >
                <Trash2 />
              </Button>
            ) : !i.is_active ? (
              <span className='ms-auto text-xs text-muted-foreground'>
                deactivated
              </span>
            ) : null}
          </li>
        ))}
        {!item.identifiers?.length ? (
          <li className='text-muted-foreground'>No scan tags yet.</li>
        ) : null}
      </ul>
      {editable ? (
        <form
          className='flex gap-2'
          onSubmit={(e) => {
            e.preventDefault()
            add.mutate(undefined, { onSuccess: () => setValue('') })
          }}
        >
          <NativeSelect
            aria-label='Tag kind'
            className='w-28'
            values={IDENTIFIER_KINDS}
            value={kind}
            onChange={(e) => setKind(e.target.value)}
          />
          <Input
            aria-label='Tag value'
            placeholder='Scan or type the code'
            value={value}
            onChange={(e) => setValue(e.target.value)}
          />
          <Button type='submit' disabled={!value.trim() || add.isPending}>
            Add
          </Button>
        </form>
      ) : null}
    </div>
  )
}

function ItemDetails({
  projectId,
  item,
  type,
}: {
  projectId: number
  item: Item
  type: ItemType | undefined
}) {
  const session = useSession()
  const editable = can(session, 'asset_tree.update')
  const [values, setValues] = useState({
    tag: item.tag,
    spec_ref: item.spec_ref ?? '',
    discipline: item.discipline ?? '',
    status: item.status,
    notes: item.notes ?? '',
  })
  const [custom, setCustom] = useState<Record<string, unknown>>(
    item.custom_fields ?? {}
  )
  const save = useTreeWrite(projectId, () =>
    unwrap(
      api.PATCH('/api/v1/asset-tree/items/{item_id}', {
        params: { path: { item_id: item.id } },
        body: {
          tag: values.tag.trim(),
          spec_ref: values.spec_ref || null,
          discipline: values.discipline || null,
          status: values.status || null,
          notes: values.notes || null,
          custom_fields: custom,
        },
      })
    )
  )
  const text = (key: keyof typeof values, label: string) => (
    <div className='grid gap-1'>
      <Label htmlFor={`item-${key}`}>{label}</Label>
      <Input
        id={`item-${key}`}
        readOnly={!editable}
        value={values[key]}
        onChange={(e) => setValues({ ...values, [key]: e.target.value })}
      />
    </div>
  )
  return (
    <form
      className='grid gap-3'
      onSubmit={(e) => {
        e.preventDefault()
        save.mutate(undefined)
      }}
    >
      <p className='text-sm text-muted-foreground'>{item.node_display_path}</p>
      <div className='grid grid-cols-2 gap-3'>
        {text('tag', 'Tag')}
        {text('status', 'Status')}
        {text('spec_ref', 'Spec ref.')}
        {text('discipline', 'Discipline')}
      </div>
      {type ? (
        <>
          <h4 className='text-sm font-medium'>
            {type.name} fields{' '}
            <span className='text-xs font-normal text-muted-foreground'>
              (revision {item.type_revision}
              {item.type_revision !== type.revision
                ? `, type is now at ${type.revision}`
                : ''}
              )
            </span>
          </h4>
          <SchemaFieldsEditor
            idPrefix={`item-${item.id}`}
            fields={schemaFields(type.field_schema)}
            value={custom}
            onChange={setCustom}
            readOnly={!editable}
          />
        </>
      ) : null}
      <div className='grid gap-1'>
        <Label htmlFor='item-notes'>Notes</Label>
        <Textarea
          id='item-notes'
          readOnly={!editable}
          value={values.notes}
          onChange={(e) => setValues({ ...values, notes: e.target.value })}
        />
      </div>
      {editable ? (
        <Button
          type='submit'
          size='sm'
          className='w-fit'
          disabled={save.isPending}
        >
          Save
        </Button>
      ) : null}
    </form>
  )
}

export function ItemSheet({
  projectId,
  id,
  onClose,
  term,
}: {
  projectId: number
  id: number | null
  onClose: () => void
  term: TermFn
}) {
  const { data: item } = useItem(id)
  const { data: types = [] } = useItemTypes(projectId)
  const type = types.find((t) => t.key === item?.item_type_key)
  return (
    <RecordSheet
      open={Boolean(id)}
      onClose={onClose}
      title={item ? item.tag : term('noun.item')}
      subtitle={type?.name}
      badges={item ? <StatusBadge status={item.status} /> : null}
      record={
        item
          ? { projectId, entityType: 'asset_item', entityId: item.id }
          : undefined
      }
      tabs={
        item
          ? {
              [term('noun.identifier', 2)]: (
                <Identifiers projectId={projectId} item={item} />
              ),
            }
          : undefined
      }
    >
      {item ? (
        <ItemDetails
          key={JSON.stringify(item)}
          projectId={projectId}
          item={item}
          type={type}
        />
      ) : null}
    </RecordSheet>
  )
}

/** The items in the selected node's subtree (or the whole project), filterable by type, with saved views. */
export function ItemsGrid({
  projectId,
  node,
  term,
  onOpen,
}: {
  projectId: number
  node: TreeNode | null
  term: TermFn
  onOpen: (id: number) => void
}) {
  const session = useSession()
  const [itemType, setItemType] = useState('')
  const [creating, setCreating] = useState(false)
  const { data: types = [] } = useItemTypes(projectId)
  const { data: rows = [] } = useItems(projectId, node?.id ?? null, itemType)
  const views = useSavedViews<Item>('asset_tree.items', projectId)
  const typeName = useMemo(
    () => Object.fromEntries(types.map((t) => [t.key, t.name])),
    [types]
  )
  const columns = useMemo<ColDef<Item>[]>(() => {
    const extra = schemaFields(
      types.find((t) => t.key === itemType)?.field_schema
    ).map(
      (f): ColDef<Item> => ({
        colId: `custom_fields.${f.key}`,
        headerName: f.title,
        width: 130,
        valueGetter: (p) => p.data?.custom_fields?.[f.key] as string,
      })
    )
    return [
      { field: 'tag', headerName: 'Tag', width: 140, cellClass: 'font-mono' },
      {
        field: 'item_type_key',
        headerName: term('noun.item_type'),
        width: 150,
        valueFormatter: (p) => typeName[p.value as string] ?? p.value,
      },
      {
        field: 'node_display_path',
        headerName: term('noun.node'),
        flex: 1,
        minWidth: 200,
      },
      { field: 'spec_ref', headerName: 'Spec ref.', width: 110 },
      { field: 'discipline', headerName: 'Discipline', width: 110 },
      {
        field: 'status',
        headerName: 'Status',
        width: 110,
        cellRenderer: (p: { value: string }) => (
          <StatusBadge status={p.value} />
        ),
      },
      {
        colId: 'identifiers',
        headerName: term('noun.identifier', 2),
        width: 160,
        valueGetter: (p) =>
          (p.data?.identifiers ?? [])
            .filter((i) => i.is_active)
            .map((i) => i.value)
            .join(', '),
      },
      ...extra,
    ]
  }, [types, itemType, typeName, term])
  return (
    <div className='grid gap-2'>
      <div className='flex flex-wrap items-center gap-2'>
        <SavedViewsMenu views={views} />
        <NativeSelect
          aria-label={term('noun.item_type')}
          className='h-8 w-48'
          placeholder={`All ${term('noun.item_type', 2).toLowerCase()}`}
          options={types.map((t) => ({ value: t.key, label: t.name }))}
          value={itemType}
          onChange={(e) => setItemType(e.target.value)}
        />
        <span className='text-sm text-muted-foreground'>
          {rows.length} {term('noun.item', rows.length).toLowerCase()}
          {node ? ` under ${node.display_path}` : ' in the project'}
        </span>
        {node &&
        can(session, 'asset_tree.create') &&
        node.status !== 'retired' ? (
          <Button
            size='sm'
            className='ms-auto'
            onClick={() => setCreating(true)}
          >
            <Plus /> New {term('noun.item').toLowerCase()}
          </Button>
        ) : null}
      </div>
      <div className='h-[480px]'>
        <DataGrid<Item>
          onGridReady={views.onGridReady}
          rowData={rows}
          columnDefs={columns}
          getRowId={(p) => String(p.data.id)}
          rowClass='cursor-pointer'
          onRowClicked={(e) => e.data && onOpen(e.data.id)}
        />
      </div>
      {creating && node ? (
        <NewItem
          projectId={projectId}
          node={node}
          types={types}
          term={term}
          onClose={() => setCreating(false)}
          onCreated={onOpen}
        />
      ) : null}
    </div>
  )
}
