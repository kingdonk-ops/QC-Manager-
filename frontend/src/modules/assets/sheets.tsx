import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api, unwrap } from '@/api/client'
import { can, useSession } from '@/lib/session'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { RecordSheet } from '@/components/records/record-sheet'
import { statusLabel } from '@/components/records/status'
import { StatusBadge } from '@/components/records/status-badge'
import {
  STATUSES,
  useContacts,
  useSpaces,
  useSystems,
  useTypes,
  useWrite,
  type AssetType,
  type Component,
} from './api'
import { AttributesEditor } from './attributes-editor'
import { FieldForm, type Field } from './field-form'

function History({ id }: { id: number }) {
  const { data = [] } = useQuery({
    queryKey: ['assets', 'history', id],
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/assets/components/{row_id}/history', {
          params: { path: { row_id: id } },
        })
      ),
  })
  if (!data.length)
    return (
      <p className='text-sm text-muted-foreground'>No status changes yet.</p>
    )
  return (
    <ul className='grid gap-2 text-sm'>
      {data.map((h, i) => (
        <li key={i} className='flex items-center gap-2'>
          <StatusBadge status={String(h.from_status ?? '')} />→
          <StatusBadge status={String(h.to_status)} />
          <span className='ms-auto text-xs text-muted-foreground'>
            {h.changed_at
              ? new Date(String(h.changed_at)).toLocaleString()
              : ''}
          </span>
        </li>
      ))}
    </ul>
  )
}

function Systems({
  projectId,
  component,
}: {
  projectId: number
  component: Component
}) {
  const session = useSession()
  const { data: systems = [] } = useSystems(projectId)
  const write = useWrite(projectId)
  const member = new Set(component.system_ids)
  if (!systems.length)
    return (
      <p className='text-sm text-muted-foreground'>
        No systems yet; add them on the Systems tab.
      </p>
    )
  return (
    <div className='grid gap-2'>
      {systems.map((s) => (
        <label key={s.id} className='flex items-center gap-2 text-sm'>
          <Checkbox
            disabled={!can(session, 'assets.update')}
            checked={member.has(s.id)}
            onCheckedChange={(on) => {
              const next = on
                ? [...member, s.id]
                : [...member].filter((id) => id !== s.id)
              write.mutate({
                kind: 'components',
                id: component.id,
                body: { system_ids: next },
              })
            }}
          />
          {s.name}
          <span className='text-xs text-muted-foreground'>{s.category}</span>
        </label>
      ))}
    </div>
  )
}

export function ComponentSheet({
  projectId,
  component,
  onClose,
}: {
  projectId: number
  component: Component | null
  onClose: () => void
}) {
  const session = useSession()
  const write = useWrite(projectId)
  const { data: types = [] } = useTypes(projectId)
  const { data: spaces = [] } = useSpaces(projectId)
  if (!component) return null
  const readOnly = !can(session, 'assets.update')
  const fields: Field[] = [
    { key: 'name', label: 'Name / tag' },
    {
      key: 'status',
      label: 'Status',
      kind: 'select',
      required: true,
      options: STATUSES.map((s) => [s, statusLabel(s)]),
    },
    {
      key: 'type_id',
      label: 'Type',
      kind: 'select',
      options: types.map((t) => [String(t.id), t.name]),
    },
    {
      key: 'space_id',
      label: 'Space',
      kind: 'select',
      options: spaces.map((s) => [String(s.id), s.name]),
    },
    { key: 'serial_number', label: 'Serial number' },
    { key: 'asset_identifier', label: 'Asset identifier' },
    { key: 'tag_number', label: 'Tag number' },
    { key: 'bar_code', label: 'Barcode' },
    { key: 'installation_date', label: 'Installed', kind: 'date' },
    { key: 'warranty_start_date', label: 'Warranty start', kind: 'date' },
    { key: 'description', label: 'Description', kind: 'textarea' },
  ]
  return (
    <RecordSheet
      open
      onClose={onClose}
      wide
      title={component.name}
      subtitle={
        [component.type_name, component.space_name, component.floor_name]
          .filter(Boolean)
          .join(' · ') || 'No type or space yet'
      }
      badges={<StatusBadge status={component.status} />}
      record={{ projectId, entityType: 'asset', entityId: component.id }}
      tabs={{
        Attributes: (
          <AttributesEditor
            key={component.id}
            value={component.attributes ?? {}}
            readOnly={readOnly}
            onSave={(attributes) =>
              write.mutate({
                kind: 'components',
                id: component.id,
                body: { attributes },
              })
            }
          />
        ),
        Systems: <Systems projectId={projectId} component={component} />,
        History: <History id={component.id} />,
      }}
    >
      <FieldForm
        key={`${component.id}-${component.status}-${component.type_id}-${component.space_id}`}
        fields={fields}
        record={component as unknown as Record<string, unknown>}
        readOnly={readOnly}
        saving={write.isPending}
        onSave={(body) =>
          write.mutate({ kind: 'components', id: component.id, body })
        }
      />
    </RecordSheet>
  )
}

export function TypeSheet({
  projectId,
  type,
  onClose,
}: {
  projectId: number
  type: AssetType | null
  onClose: () => void
}) {
  const session = useSession()
  const write = useWrite(projectId)
  const [search, setSearch] = useState('')
  const { data: contacts = [] } = useContacts(search)
  if (!type) return null
  const readOnly = !can(session, 'assets.update')
  const people: [string, string][] = contacts.map((c) => [
    String(c.id),
    c.company_name
      ? `${c.full_name} (${c.company_name})`
      : c.full_name || String(c.id),
  ])
  for (const [id, name] of [
    [type.manufacturer_id, type.manufacturer_name],
    [type.warranty_guarantor_id, type.warranty_guarantor_name],
  ] as const)
    if (id && !people.some(([v]) => v === String(id)))
      people.push([String(id), name ?? `Contact ${id}`])
  const fields: Field[] = [
    { key: 'name', label: 'Name' },
    { key: 'category', label: 'Category (Uniclass / OmniClass)' },
    {
      key: 'asset_kind',
      label: 'Asset type',
      kind: 'select',
      required: true,
      options: [
        ['Fixed', 'Fixed'],
        ['Moveable', 'Moveable'],
      ],
    },
    { key: 'model_number', label: 'Model number' },
    {
      key: 'manufacturer_id',
      label: 'Manufacturer',
      kind: 'select',
      options: people,
    },
    {
      key: 'warranty_guarantor_id',
      label: 'Warranty guarantor',
      kind: 'select',
      options: people,
    },
    {
      key: 'warranty_duration_parts',
      label: 'Warranty, parts (years)',
      kind: 'number',
    },
    {
      key: 'warranty_duration_labor',
      label: 'Warranty, labour (years)',
      kind: 'number',
    },
    { key: 'replacement_cost', label: 'Replacement cost', kind: 'number' },
    { key: 'expected_life', label: 'Expected life (years)', kind: 'number' },
    { key: 'nominal_length', label: 'Nominal length', kind: 'number' },
    { key: 'nominal_width', label: 'Nominal width', kind: 'number' },
    { key: 'nominal_height', label: 'Nominal height', kind: 'number' },
    { key: 'material', label: 'Material' },
    { key: 'color', label: 'Colour' },
    { key: 'finish', label: 'Finish' },
    {
      key: 'warranty_description',
      label: 'Warranty description',
      kind: 'textarea',
    },
    { key: 'description', label: 'Description', kind: 'textarea' },
  ]
  return (
    <RecordSheet
      open
      onClose={onClose}
      wide
      title={type.name}
      subtitle={`${type.component_count} components${type.manufacturer_name ? ` · ${type.manufacturer_name}` : ''}`}
      record={{ projectId, entityType: 'asset_type', entityId: type.id }}
      tabs={{
        Attributes: (
          <AttributesEditor
            key={type.id}
            value={type.attributes ?? {}}
            readOnly={readOnly}
            onSave={(attributes) =>
              write.mutate({ kind: 'types', id: type.id, body: { attributes } })
            }
          />
        ),
      }}
    >
      {!readOnly ? (
        <Input
          className='mb-3 h-8'
          placeholder='Find a manufacturer or guarantor in Contacts'
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      ) : null}
      <FieldForm
        key={type.id}
        fields={fields}
        record={type as unknown as Record<string, unknown>}
        readOnly={readOnly}
        saving={write.isPending}
        onSave={(body) =>
          write.mutate({
            kind: 'types',
            id: type.id,
            body:
              'replacement_cost' in body && body.replacement_cost !== null
                ? { ...body, replacement_cost: String(body.replacement_cost) }
                : body,
          })
        }
      />
    </RecordSheet>
  )
}
