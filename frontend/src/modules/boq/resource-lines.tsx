import { useEffect, useRef, useState } from 'react'
import { Boxes, Plus, Trash2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover'
import {
  type Assembly,
  type Line,
  type Position,
  type Resource,
  useAssemblies,
  useBillActions,
  useResources,
} from './api'
import { LINE_HEIGHT, fmt } from './format'
import { parseNumber } from './tree'

type PickerProps<T> = {
  placeholder: string
  icon: React.ReactNode
  onPick: (item: T) => void
  disabled?: boolean
}

/** A button opening a search box with a dropdown of matches; picking one calls `onPick`. */
function Picker<T extends { id: number }>({
  placeholder,
  icon,
  label,
  detail,
  onPick,
  disabled,
  items,
  search,
  setSearch,
}: PickerProps<T> & {
  label: (item: T) => string
  detail: (item: T) => string
  items: T[]
  search: string
  setSearch: (search: string) => void
}) {
  const [open, setOpen] = useState(false)
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button size='sm' variant='outline' className='h-7' disabled={disabled}>
          {icon} {placeholder}
        </Button>
      </PopoverTrigger>
      <PopoverContent className='w-96 p-2' align='start'>
        <Input
          autoFocus
          className='mb-2 h-8'
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder={placeholder}
        />
        <ul className='max-h-64 overflow-auto text-sm'>
          {items.map((item) => (
            <li key={item.id}>
              <button
                type='button'
                className='flex w-full items-center justify-between gap-2 rounded px-2 py-1 text-start hover:bg-accent'
                onClick={() => {
                  onPick(item)
                  setOpen(false)
                  setSearch('')
                }}
              >
                <span className='truncate'>{label(item)}</span>
                <span className='shrink-0 text-xs text-muted-foreground tabular-nums'>
                  {detail(item)}
                </span>
              </button>
            </li>
          ))}
        </ul>
      </PopoverContent>
    </Popover>
  )
}

/** Pick a resource from the catalog (with the project's overrides). */
export function ResourcePicker({
  projectId,
  ...props
}: PickerProps<Resource> & { projectId: number | null }) {
  const [search, setSearch] = useState('')
  const { data } = useResources({ search, projectId, perPage: 30 })
  return (
    <Picker<Resource>
      {...props}
      items={data?.data ?? []}
      search={search}
      setSearch={setSearch}
      label={(r) => `${r.code} · ${r.name}`}
      detail={(r) => `${fmt(r.rate)} ${r.currency}/${r.unit || '—'}`}
    />
  )
}

function AssemblyPicker({
  projectId,
  ...props
}: PickerProps<Assembly> & { projectId: number }) {
  const [search, setSearch] = useState('')
  const { data } = useAssemblies({ search, projectId })
  return (
    <Picker<Assembly>
      {...props}
      items={data?.data ?? []}
      search={search}
      setSearch={setSearch}
      label={(a) => `${a.code} · ${a.name}`}
      detail={(a) => `${fmt(a.unit_rate)}/${a.unit || '—'}`}
    />
  )
}

/** A number input that saves on blur or Enter, only when the value changed. */
export function NumberCell({
  value,
  placeholder,
  disabled,
  onSave,
}: {
  value: string | null
  placeholder?: string
  disabled?: boolean
  onSave: (value: string | null) => void
}) {
  const display = value === null ? '' : String(Number(value))
  const [text, setText] = useState(display)
  const [shown, setShown] = useState(value)
  if (shown !== value) {
    setShown(value)
    setText(display)
  }
  const commit = () => {
    const parsed = text.trim() === '' ? null : parseNumber(text)
    if (text.trim() !== '' && parsed === null) return setText(display)
    if (
      parsed === value ||
      (parsed !== null && value !== null && Number(parsed) === Number(value))
    )
      return
    onSave(parsed)
  }
  return (
    <Input
      className='ms-auto h-6 w-24 px-1 text-end text-xs tabular-nums'
      value={text}
      disabled={disabled}
      placeholder={placeholder}
      onChange={(e) => setText(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => {
        if (e.key === 'Enter') (e.target as HTMLInputElement).blur()
      }}
    />
  )
}

/** The expanded row under a position: its resource lines, live unit rate, add resource / apply assembly. */
export function ResourceLines({
  boqId,
  projectId,
  position,
  editable,
  currency,
}: {
  boqId: number
  projectId: number
  position: Position
  editable: boolean
  currency: string
}) {
  const { t } = useTranslation()
  const actions = useBillActions(boqId)
  const panel = useRef<HTMLDivElement>(null)
  const lines: Line[] = position.resources

  // Keys typed here belong to the inputs, not to the grid's cell navigation.
  useEffect(() => {
    const el = panel.current
    if (!el) return
    const stop = (e: Event) => e.stopPropagation()
    el.addEventListener('keydown', stop)
    el.addEventListener('paste', stop)
    return () => {
      el.removeEventListener('keydown', stop)
      el.removeEventListener('paste', stop)
    }
  }, [])

  return (
    <div
      ref={panel}
      className='h-full overflow-hidden border-y bg-muted/40 py-2 pe-4 text-xs'
      style={{ paddingInlineStart: 48 + position.depth * 16 }}
    >
      <div className='mb-1 flex items-center gap-2' style={{ height: 32 }}>
        <span className='font-semibold'>{t('boq.resources')}</span>
        <span className='text-muted-foreground'>
          {position.ordinal} · {position.unit || '—'}
        </span>
        {editable ? (
          <>
            <ResourcePicker
              projectId={projectId}
              placeholder={t('boq.add_resource')}
              icon={<Plus />}
              onPick={(r) =>
                actions.addLine.mutate({
                  id: position.id,
                  resource_id: r.id,
                  factor: '1',
                  waste_pct: '0',
                })
              }
            />
            <AssemblyPicker
              projectId={projectId}
              placeholder={t('boq.apply_assembly')}
              icon={<Boxes />}
              onPick={(a) =>
                actions.applyAssembly.mutate({
                  id: position.id,
                  assemblyId: a.id,
                })
              }
            />
          </>
        ) : null}
        <span className='ms-auto font-medium tabular-nums'>
          {t('boq.col.rate')}:{' '}
          {position.unit_rate === null
            ? '—'
            : `${fmt(position.unit_rate)} ${currency}`}
        </span>
      </div>
      {lines.length === 0 ? (
        <p
          className='text-muted-foreground'
          style={{ lineHeight: `${LINE_HEIGHT}px` }}
        >
          {t('boq.no_lines')}
        </p>
      ) : (
        <table className='w-full table-fixed'>
          <thead className='text-muted-foreground'>
            <tr style={{ height: LINE_HEIGHT }}>
              <th className='w-28 text-start font-medium'>
                {t('boq.col.code')}
              </th>
              <th className='text-start font-medium'>{t('boq.field.name')}</th>
              <th className='w-16 text-start font-medium'>
                {t('boq.col.unit')}
              </th>
              <th className='w-28 text-end font-medium'>{t('boq.factor')}</th>
              <th className='w-28 text-end font-medium'>{t('boq.waste')}</th>
              <th className='w-28 text-end font-medium'>
                {t('boq.rate_override')}
              </th>
              <th className='w-28 text-end font-medium'>{t('boq.cost')}</th>
              <th className='w-8' />
            </tr>
          </thead>
          <tbody>
            {lines.map((line) => (
              <tr key={line.id} style={{ height: LINE_HEIGHT }}>
                <td className='truncate font-mono'>{line.code}</td>
                <td className='truncate'>
                  {line.name}{' '}
                  <span className='text-muted-foreground'>
                    ({t(`boq.type.${line.type}`)})
                  </span>
                </td>
                <td>{line.unit}</td>
                <td>
                  <NumberCell
                    value={line.factor}
                    disabled={!editable}
                    onSave={(v) =>
                      actions.updateLine.mutate({
                        id: position.id,
                        lineId: line.id,
                        factor: v ?? '0',
                      })
                    }
                  />
                </td>
                <td>
                  <NumberCell
                    value={line.waste_pct}
                    disabled={!editable}
                    onSave={(v) =>
                      actions.updateLine.mutate({
                        id: position.id,
                        lineId: line.id,
                        waste_pct: v ?? '0',
                      })
                    }
                  />
                </td>
                <td>
                  <NumberCell
                    value={line.rate_override}
                    placeholder={fmt(line.catalog_rate)}
                    disabled={!editable}
                    onSave={(v) =>
                      actions.updateLine.mutate({
                        id: position.id,
                        lineId: line.id,
                        rate_override: v,
                      })
                    }
                  />
                </td>
                <td className='text-end tabular-nums'>{fmt(line.cost)}</td>
                <td className='text-end'>
                  {editable ? (
                    <button
                      type='button'
                      aria-label={t('boq.delete')}
                      className='text-muted-foreground hover:text-red-600'
                      onClick={() =>
                        actions.removeLine.mutate({
                          id: position.id,
                          lineId: line.id,
                        })
                      }
                    >
                      <Trash2 className='size-3.5' />
                    </button>
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
