import { useRef, useState } from 'react'
import { Camera, X } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { NativeSelect } from '@/components/native-select'
import { fileUrl, uploadFile } from '@/components/records/files'
import type { FieldDef } from './workflow'

export type Answers = Record<string, unknown>

/** Photos as file ids: take or pick pictures (the phone's camera on mobile), shown as thumbnails. */
export function PhotoInput({
  value,
  onChange,
  projectId,
  entity,
  disabled,
  label = 'Add photo',
}: {
  value: number[]
  onChange: (ids: number[]) => void
  projectId: number
  entity?: { type: string; id: number }
  disabled?: boolean
  label?: string
}) {
  const input = useRef<HTMLInputElement>(null)
  const [busy, setBusy] = useState(false)
  async function add(files: FileList) {
    setBusy(true)
    try {
      const ids: number[] = []
      for (const file of Array.from(files)) {
        const form = new FormData()
        form.set('file', file)
        form.set('project_id', String(projectId))
        form.set('category', 'photo')
        if (entity) {
          form.set('entity_type', entity.type)
          form.set('entity_id', String(entity.id))
        }
        ids.push((await uploadFile(form)).id)
      }
      onChange([...value, ...ids])
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Upload failed')
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className='flex flex-wrap items-center gap-2'>
      {value.map((id) => (
        <span key={id} className='relative'>
          <a href={fileUrl(id, true)} target='_blank' rel='noreferrer'>
            <img
              src={fileUrl(id, true)}
              alt=''
              className='size-16 rounded-md border object-cover'
            />
          </a>
          {disabled ? null : (
            <button
              type='button'
              aria-label='Remove photo'
              className='absolute -end-1.5 -top-1.5 rounded-full bg-background p-0.5 shadow'
              onClick={() => onChange(value.filter((v) => v !== id))}
            >
              <X className='size-3' />
            </button>
          )}
        </span>
      ))}
      {disabled ? null : (
        <>
          <input
            ref={input}
            type='file'
            accept='image/*'
            capture='environment'
            multiple
            hidden
            onChange={(e) => e.target.files?.length && add(e.target.files)}
          />
          <Button
            type='button'
            size='sm'
            variant='outline'
            className='h-16'
            disabled={busy}
            onClick={() => input.current?.click()}
          >
            <Camera /> {label}
          </Button>
        </>
      )}
    </div>
  )
}

function FieldInput({
  field,
  value,
  onChange,
  disabled,
  projectId,
  entity,
}: {
  field: FieldDef
  value: unknown
  onChange: (value: unknown) => void
  disabled: boolean
  projectId: number
  entity?: { type: string; id: number }
}) {
  const id = `issue-field-${field.key}`
  switch (field.type) {
    case 'textarea':
      return (
        <Textarea
          id={id}
          disabled={disabled}
          value={(value as string) ?? ''}
          onChange={(e) => onChange(e.target.value)}
        />
      )
    case 'number':
      return (
        <Input
          id={id}
          type='number'
          inputMode='decimal'
          disabled={disabled}
          min={field.min ?? undefined}
          max={field.max ?? undefined}
          value={value === null || value === undefined ? '' : String(value)}
          onChange={(e) =>
            onChange(e.target.value === '' ? null : Number(e.target.value))
          }
        />
      )
    case 'date':
      return (
        <Input
          id={id}
          type='date'
          disabled={disabled}
          value={(value as string) ?? ''}
          onChange={(e) => onChange(e.target.value || null)}
        />
      )
    case 'select':
      return (
        <NativeSelect
          id={id}
          disabled={disabled}
          placeholder='—'
          options={(field.options ?? []).map((o) => ({ value: o, label: o }))}
          value={(value as string) ?? ''}
          onChange={(e) => onChange(e.target.value || null)}
        />
      )
    case 'multiselect': {
      const picked = (value as string[]) ?? []
      return (
        <div className='flex flex-wrap gap-3'>
          {(field.options ?? []).map((o) => (
            <label key={o} className='flex items-center gap-1.5 text-sm'>
              <Checkbox
                disabled={disabled}
                checked={picked.includes(o)}
                onCheckedChange={(on) =>
                  onChange(on ? [...picked, o] : picked.filter((p) => p !== o))
                }
              />
              {o}
            </label>
          ))}
        </div>
      )
    }
    case 'checkbox':
      return (
        <Checkbox
          id={id}
          disabled={disabled}
          checked={Boolean(value)}
          onCheckedChange={(on) => onChange(on === true)}
        />
      )
    case 'photo':
      return (
        <PhotoInput
          value={(value as number[]) ?? []}
          onChange={onChange}
          projectId={projectId}
          entity={entity}
          disabled={disabled}
        />
      )
    default:
      return (
        <Input
          id={id}
          disabled={disabled}
          value={(value as string) ?? ''}
          onChange={(e) => onChange(e.target.value)}
        />
      )
  }
}

/** Inputs for a template's fields. `editable` decides per field (completed steps are read-only). */
export function TemplateFields({
  fields,
  values,
  onChange,
  editable,
  projectId,
  entity,
}: {
  fields: FieldDef[]
  values: Answers
  onChange: (key: string, value: unknown) => void
  editable: (field: FieldDef) => boolean
  projectId: number
  entity?: { type: string; id: number }
}) {
  return (
    <div className='grid gap-3 sm:grid-cols-2'>
      {fields.map((f) => (
        <div
          key={f.key}
          className={
            f.type === 'textarea' ||
            f.type === 'photo' ||
            f.type === 'multiselect'
              ? 'grid gap-1.5 sm:col-span-2'
              : 'grid gap-1.5'
          }
        >
          <Label htmlFor={`issue-field-${f.key}`}>
            {f.label}
            {f.unit ? ` (${f.unit})` : ''}
            {f.required ? <span className='text-red-600'> *</span> : null}
          </Label>
          <FieldInput
            field={f}
            value={values[f.key]}
            onChange={(v) => onChange(f.key, v)}
            disabled={!editable(f)}
            projectId={projectId}
            entity={entity}
          />
          {f.help ? (
            <p className='text-xs text-muted-foreground'>{f.help}</p>
          ) : null}
        </div>
      ))}
    </div>
  )
}
