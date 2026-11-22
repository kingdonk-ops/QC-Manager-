import { useState } from 'react'
import { Plus, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'

type Row = { id: number; key: string; value: string }
let nextId = 1

/** Key/value attributes (COBie Attribute rows). Saves the whole set when a row changes. */
export function AttributesEditor({
  value,
  onSave,
  readOnly,
}: {
  value: Record<string, string>
  onSave: (next: Record<string, string>) => void
  readOnly?: boolean
}) {
  const [rows, setRows] = useState<Row[]>(() =>
    Object.entries(value).map(([key, v]) => ({ id: nextId++, key, value: v }))
  )
  const commit = (next: Row[]) => {
    setRows(next)
    const clean = Object.fromEntries(
      next.filter((r) => r.key.trim()).map((r) => [r.key.trim(), r.value])
    )
    if (JSON.stringify(clean) !== JSON.stringify(value)) onSave(clean)
  }
  const change = (id: number, patch: Partial<Row>) =>
    commit(rows.map((r) => (r.id === id ? { ...r, ...patch } : r)))
  return (
    <div className='grid gap-1.5'>
      {rows.length === 0 ? (
        <p className='text-sm text-muted-foreground'>No attributes yet.</p>
      ) : null}
      {rows.map((row) => (
        <div key={row.id} className='flex gap-1.5'>
          <Input
            className='h-8'
            aria-label='Attribute name'
            placeholder='Name, e.g. Flow rate'
            defaultValue={row.key}
            readOnly={readOnly}
            onBlur={(e) => change(row.id, { key: e.target.value })}
          />
          <Input
            className='h-8'
            aria-label='Attribute value'
            placeholder='Value'
            defaultValue={row.value}
            readOnly={readOnly}
            onBlur={(e) => change(row.id, { value: e.target.value })}
          />
          {!readOnly ? (
            <Button
              size='icon'
              variant='ghost'
              className='size-8 shrink-0'
              aria-label='Remove attribute'
              onClick={() => commit(rows.filter((r) => r.id !== row.id))}
            >
              <Trash2 className='size-4' />
            </Button>
          ) : null}
        </div>
      ))}
      {!readOnly ? (
        <Button
          size='sm'
          variant='outline'
          className='w-fit'
          onClick={() =>
            setRows((r) => [...r, { id: nextId++, key: '', value: '' }])
          }
        >
          <Plus /> Add attribute
        </Button>
      ) : null}
    </div>
  )
}
