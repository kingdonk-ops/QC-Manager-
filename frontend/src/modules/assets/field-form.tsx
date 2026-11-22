import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'

export type Field = {
  key: string
  label: string
  kind?: 'text' | 'number' | 'date' | 'textarea' | 'select'
  /** For selects: value → label. An empty value clears the field. */
  options?: [string, string][]
  wide?: boolean
  /** Selects only: no blank choice. */
  required?: boolean
}

const NONE = '__none__'

/** A two-column form over a record; Save sends only the fields that changed. */
export function FieldForm({
  fields,
  record,
  onSave,
  saving,
  readOnly,
}: {
  fields: Field[]
  record: Record<string, unknown>
  onSave: (changes: Record<string, unknown>) => void
  saving?: boolean
  readOnly?: boolean
}) {
  const text = (v: unknown) => (v === null || v === undefined ? '' : String(v))
  const [values, setValues] = useState<Record<string, string>>(() =>
    Object.fromEntries(fields.map((f) => [f.key, text(record[f.key])]))
  )
  const changes = () => {
    const out: Record<string, unknown> = {}
    for (const f of fields) {
      const v = values[f.key]
      if (v === text(record[f.key])) continue
      if (v === '') out[f.key] = null
      else if (f.kind === 'number') out[f.key] = Number(v)
      else if (f.kind === 'select' && /^\d+$/.test(v) && f.key.endsWith('_id'))
        out[f.key] = Number(v)
      else out[f.key] = v
    }
    return out
  }
  const dirty = Object.keys(changes()).length > 0
  return (
    <div className='grid gap-3'>
      <div className='grid grid-cols-2 gap-3'>
        {fields.map((f) => (
          <div
            key={f.key}
            className={
              f.wide || f.kind === 'textarea'
                ? 'col-span-2 grid gap-1'
                : 'grid gap-1'
            }
          >
            <Label htmlFor={`f-${f.key}`}>{f.label}</Label>
            {f.kind === 'textarea' ? (
              <Textarea
                id={`f-${f.key}`}
                rows={3}
                readOnly={readOnly}
                value={values[f.key]}
                onChange={(e) =>
                  setValues((s) => ({ ...s, [f.key]: e.target.value }))
                }
              />
            ) : f.kind === 'select' ? (
              <Select
                disabled={readOnly}
                value={values[f.key] || NONE}
                onValueChange={(v) =>
                  setValues((s) => ({ ...s, [f.key]: v === NONE ? '' : v }))
                }
              >
                <SelectTrigger id={`f-${f.key}`} className='w-full'>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {!f.required ? <SelectItem value={NONE}>—</SelectItem> : null}
                  {(f.options ?? []).map(([value, label]) => (
                    <SelectItem key={value} value={value}>
                      {label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            ) : (
              <Input
                id={`f-${f.key}`}
                type={f.kind ?? 'text'}
                step='any'
                readOnly={readOnly}
                value={values[f.key]}
                onChange={(e) =>
                  setValues((s) => ({ ...s, [f.key]: e.target.value }))
                }
              />
            )}
          </div>
        ))}
      </div>
      {!readOnly ? (
        <Button
          className='w-fit'
          disabled={!dirty || saving}
          onClick={() => onSave(changes())}
        >
          Save
        </Button>
      ) : null}
    </div>
  )
}
