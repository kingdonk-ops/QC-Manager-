import { useState, type ReactNode } from 'react'
import { Building2, DoorOpen, Layers, Plus, Trash2 } from 'lucide-react'
import { can, useSession } from '@/lib/session'
import { cn } from '@/lib/utils'
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
import { useTree, useWrite, type Place } from './api'

type Adding =
  | { kind: 'facilities' }
  | { kind: 'floors'; facility_id: number }
  | { kind: 'spaces'; floor_id: number }

const FIELDS: Record<
  Adding['kind'],
  { title: string; extra: [string, string][] }
> = {
  facilities: {
    title: 'Add a facility',
    extra: [
      ['category', 'Category'],
      ['site_name', 'Site name'],
    ],
  },
  floors: {
    title: 'Add a floor',
    extra: [
      ['elevation', 'Elevation (m)'],
      ['height', 'Height (m)'],
    ],
  },
  spaces: {
    title: 'Add a space',
    extra: [
      ['category', 'Category'],
      ['room_tag', 'Room tag'],
      ['gross_area', 'Gross area (m²)'],
      ['net_area', 'Net area (m²)'],
    ],
  },
}
const NUMERIC = new Set(['elevation', 'height', 'gross_area', 'net_area'])

function AddDialog({
  adding,
  projectId,
  onClose,
}: {
  adding: Adding
  projectId: number
  onClose: () => void
}) {
  const write = useWrite(projectId)
  const [values, setValues] = useState<Record<string, string>>({})
  const spec = FIELDS[adding.kind]
  const save = () => {
    const body: Record<string, unknown> = { name: values.name?.trim() }
    for (const [key] of spec.extra) {
      const v = values[key]?.trim()
      if (v) body[key] = NUMERIC.has(key) ? Number(v) : v
    }
    if ('facility_id' in adding) body.facility_id = adding.facility_id
    if ('floor_id' in adding) body.floor_id = adding.floor_id
    write.mutate({ kind: adding.kind, body }, { onSuccess: onClose })
  }
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className='sm:max-w-sm'>
        <DialogHeader>
          <DialogTitle>{spec.title}</DialogTitle>
        </DialogHeader>
        <div className='grid gap-3'>
          {[['name', 'Name'] as [string, string], ...spec.extra].map(
            ([key, label]) => (
              <div key={key} className='grid gap-1'>
                <Label htmlFor={`add-${key}`}>{label}</Label>
                <Input
                  id={`add-${key}`}
                  autoFocus={key === 'name'}
                  type={NUMERIC.has(key) ? 'number' : 'text'}
                  step='any'
                  value={values[key] ?? ''}
                  onChange={(e) =>
                    setValues((v) => ({ ...v, [key]: e.target.value }))
                  }
                />
              </div>
            )
          )}
        </div>
        <DialogFooter>
          <Button variant='outline' onClick={onClose}>
            Cancel
          </Button>
          <Button
            disabled={!values.name?.trim() || write.isPending}
            onClick={save}
          >
            Add
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function Node({
  icon,
  label,
  count,
  active,
  depth,
  onClick,
  onAdd,
  onDelete,
}: {
  icon: ReactNode
  label: string
  count: number
  active: boolean
  depth: number
  onClick: () => void
  onAdd?: () => void
  onDelete?: () => void
}) {
  return (
    <div
      className={cn(
        'group flex items-center gap-1.5 rounded-md py-1 pe-1 text-sm hover:bg-accent',
        active && 'bg-accent font-medium'
      )}
      style={{ paddingInlineStart: 6 + depth * 14 }}
    >
      <button
        className='flex min-w-0 flex-1 items-center gap-1.5 text-start'
        onClick={onClick}
      >
        {icon}
        <span className='truncate'>{label}</span>
        <span className='ms-auto text-xs text-muted-foreground tabular-nums'>
          {count}
        </span>
      </button>
      {onAdd ? (
        <button
          aria-label={`Add under ${label}`}
          className='invisible group-hover:visible'
          onClick={onAdd}
        >
          <Plus className='size-3.5' />
        </button>
      ) : null}
      {onDelete ? (
        <button
          aria-label={`Delete ${label}`}
          className='invisible group-hover:visible'
          onClick={onDelete}
        >
          <Trash2 className='size-3.5 text-muted-foreground' />
        </button>
      ) : null}
    </div>
  )
}

/** Facility → floor → space, with component counts. Picking a node filters the components. */
export function SpatialTree({
  projectId,
  place,
  onPlace,
}: {
  projectId: number
  place: Place
  onPlace: (p: Place) => void
}) {
  const session = useSession()
  const { data: tree } = useTree(projectId)
  const write = useWrite(projectId)
  const [adding, setAdding] = useState<Adding | null>(null)
  const canAdd = can(session, 'assets.create')
  const canDelete = can(session, 'assets.delete')
  const is = (kind: Place['kind'], id?: number) =>
    place.kind === kind && (!('id' in place) || place.id === id)
  const remove = (
    kind: 'facilities' | 'floors' | 'spaces',
    id: number,
    label: string
  ) => {
    if (
      window.confirm(`Delete ${label}? Its components stay, without a space.`)
    ) {
      write.mutate({ kind, id, remove: true })
      onPlace({ kind: 'all' })
    }
  }
  const total =
    (tree?.facilities.reduce((n, f) => n + f.component_count, 0) ?? 0) +
    (tree?.unplaced_components ?? 0)

  return (
    <div className='flex w-64 shrink-0 flex-col gap-1 overflow-y-auto rounded-md border p-2'>
      <div className='flex items-center justify-between px-1 pb-1'>
        <span className='text-xs font-medium tracking-wide text-muted-foreground uppercase'>
          Locations
        </span>
        {canAdd ? (
          <Button
            size='icon'
            variant='ghost'
            className='size-6'
            aria-label='Add a facility'
            onClick={() => setAdding({ kind: 'facilities' })}
          >
            <Plus className='size-3.5' />
          </Button>
        ) : null}
      </div>
      <Node
        icon={<Layers className='size-4' />}
        label='All components'
        count={total}
        depth={0}
        active={is('all')}
        onClick={() => onPlace({ kind: 'all' })}
      />
      {tree?.facilities.map((fac) => (
        <div key={fac.id}>
          <Node
            icon={<Building2 className='size-4' />}
            label={fac.name}
            count={fac.component_count}
            depth={0}
            active={is('facility', fac.id)}
            onClick={() => onPlace({ kind: 'facility', id: fac.id })}
            onAdd={
              canAdd
                ? () => setAdding({ kind: 'floors', facility_id: fac.id })
                : undefined
            }
            onDelete={
              canDelete
                ? () => remove('facilities', fac.id, fac.name)
                : undefined
            }
          />
          {fac.floors.map((fl) => (
            <div key={fl.id}>
              <Node
                icon={<Layers className='size-4 text-muted-foreground' />}
                label={fl.name}
                count={fl.component_count}
                depth={1}
                active={is('floor', fl.id)}
                onClick={() => onPlace({ kind: 'floor', id: fl.id })}
                onAdd={
                  canAdd
                    ? () => setAdding({ kind: 'spaces', floor_id: fl.id })
                    : undefined
                }
                onDelete={
                  canDelete ? () => remove('floors', fl.id, fl.name) : undefined
                }
              />
              {fl.spaces.map((sp) => (
                <Node
                  key={sp.id}
                  icon={<DoorOpen className='size-4 text-muted-foreground' />}
                  label={sp.name}
                  count={sp.component_count}
                  depth={2}
                  active={is('space', sp.id)}
                  onClick={() => onPlace({ kind: 'space', id: sp.id })}
                  onDelete={
                    canDelete
                      ? () => remove('spaces', sp.id, sp.name)
                      : undefined
                  }
                />
              ))}
            </div>
          ))}
        </div>
      ))}
      {tree && tree.unplaced_components > 0 ? (
        <Node
          icon={<Layers className='size-4 text-amber-600' />}
          label='Without a space'
          count={tree.unplaced_components}
          depth={0}
          active={is('unplaced')}
          onClick={() => onPlace({ kind: 'unplaced' })}
        />
      ) : null}
      {tree && tree.facilities.length === 0 ? (
        <p className='px-1 pt-2 text-xs text-muted-foreground'>
          Add a facility, then its floors and spaces, with the + buttons.
        </p>
      ) : null}
      {adding ? (
        <AddDialog
          adding={adding}
          projectId={projectId}
          onClose={() => setAdding(null)}
        />
      ) : null}
    </div>
  )
}
