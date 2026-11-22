import { useState } from 'react'
import { Check } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { NativeSelect } from '@/components/native-select'
import { type SchemaField, type TreeNode, useNodeSearch } from './api'
import type { TermFn } from './terminology'

/** Search every level for nodes and pick one (or several with `multiple`). */
export function NodePicker({
  projectId,
  term,
  selected,
  onChange,
  multiple,
  exclude = [],
  filter,
}: {
  projectId: number
  term: TermFn
  selected: TreeNode[]
  onChange: (nodes: TreeNode[]) => void
  multiple?: boolean
  exclude?: number[]
  filter?: (node: TreeNode) => boolean
}) {
  const [search, setSearch] = useState('')
  const { data = [], isFetching } = useNodeSearch(projectId, search)
  const ids = new Set(selected.map((n) => n.id))
  const results = data.filter(
    (n) => !exclude.includes(n.id) && (!filter || filter(n))
  )
  const toggle = (n: TreeNode) => {
    if (!multiple) return onChange(ids.has(n.id) ? [] : [n])
    onChange(
      ids.has(n.id) ? selected.filter((s) => s.id !== n.id) : [...selected, n]
    )
  }
  return (
    <div className='grid gap-2'>
      <Input
        autoFocus
        placeholder='Search by code, name or path…'
        value={search}
        onChange={(e) => setSearch(e.target.value)}
      />
      {selected.length ? (
        <div className='flex flex-wrap gap-1 text-xs'>
          {selected.map((n) => (
            <button
              type='button'
              key={n.id}
              className='rounded bg-primary/10 px-1.5 py-0.5'
              onClick={() => toggle(n)}
              title='Remove'
            >
              {n.display_path} ×
            </button>
          ))}
        </div>
      ) : null}
      <ul className='max-h-56 overflow-y-auto rounded-md border text-sm'>
        {results.map((n) => (
          <li key={n.id}>
            <button
              type='button'
              onClick={() => toggle(n)}
              className={cn(
                'flex w-full items-center gap-2 px-2 py-1 text-start hover:bg-muted',
                ids.has(n.id) && 'bg-primary/10'
              )}
            >
              {multiple ? (
                <Checkbox checked={ids.has(n.id)} tabIndex={-1} />
              ) : ids.has(n.id) ? (
                <Check className='size-4' />
              ) : (
                <span className='size-4' />
              )}
              <span className='shrink-0 text-[10px] text-muted-foreground uppercase'>
                {term(`level.${n.level_key}`)}
              </span>
              <span className='truncate'>{n.display_path}</span>
            </button>
          </li>
        ))}
        {!search.trim() ? (
          <li className='p-2 text-muted-foreground'>Type to search.</li>
        ) : !isFetching && results.length === 0 ? (
          <li className='p-2 text-muted-foreground'>No matches.</li>
        ) : null}
      </ul>
    </div>
  )
}

/** Inputs for the custom fields a level's or item type's JSONSchema declares. */
export function SchemaFieldsEditor({
  fields,
  value,
  onChange,
  readOnly,
  idPrefix,
}: {
  fields: SchemaField[]
  value: Record<string, unknown>
  onChange: (next: Record<string, unknown>) => void
  readOnly?: boolean
  idPrefix: string
}) {
  if (!fields.length) return null
  const set = (key: string, v: unknown) =>
    onChange({ ...value, [key]: v === '' ? null : v })
  return (
    <div className='grid grid-cols-2 gap-3'>
      {fields.map((f) => {
        const id = `${idPrefix}-${f.key}`
        const current = value[f.key]
        return (
          <div key={f.key} className='grid gap-1'>
            {f.type === 'boolean' ? (
              <label className='flex items-center gap-2 pt-5 text-sm'>
                <Checkbox
                  id={id}
                  disabled={readOnly}
                  checked={current === true}
                  onCheckedChange={(c) => set(f.key, c === true)}
                />
                {f.title}
              </label>
            ) : (
              <>
                <Label htmlFor={id}>{f.title}</Label>
                {f.type === 'enum' ? (
                  <NativeSelect
                    id={id}
                    disabled={readOnly}
                    placeholder='—'
                    options={(f.options ?? []).map((o) => ({
                      value: o,
                      label: o,
                    }))}
                    value={current == null ? '' : String(current)}
                    onChange={(e) => set(f.key, e.target.value)}
                  />
                ) : (
                  <Input
                    id={id}
                    readOnly={readOnly}
                    type={
                      f.type === 'date'
                        ? 'date'
                        : f.type === 'number' || f.type === 'integer'
                          ? 'number'
                          : 'text'
                    }
                    step='any'
                    value={current == null ? '' : String(current)}
                    onChange={(e) =>
                      set(
                        f.key,
                        (f.type === 'number' || f.type === 'integer') &&
                          e.target.value !== ''
                          ? Number(e.target.value)
                          : e.target.value
                      )
                    }
                  />
                )}
              </>
            )}
          </div>
        )
      })}
    </div>
  )
}
