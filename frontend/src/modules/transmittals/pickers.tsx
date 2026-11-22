import { useState } from 'react'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { StatusBadge } from '@/components/records/status-badge'
import { useContactOptions, useProjectDocuments } from './api'

/** Project documents to tick; the latest revisions by default, superseded ones on request and flagged. */
export function DocumentPicker({
  projectId,
  selected,
  onChange,
  exclude = [],
}: {
  projectId: number
  selected: number[]
  onChange: (ids: number[]) => void
  exclude?: number[]
}) {
  const { data: files = [] } = useProjectDocuments(projectId)
  const [superseded, setSuperseded] = useState(false)
  const [search, setSearch] = useState('')
  const shown = files.filter(
    (f) =>
      (superseded || f.is_latest) &&
      !exclude.includes(f.id) &&
      f.name.toLowerCase().includes(search.toLowerCase())
  )
  return (
    <div className='grid gap-2'>
      <div className='flex items-center gap-3'>
        <Input
          className='h-8'
          placeholder='Find a document'
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <label className='flex shrink-0 items-center gap-1.5 text-sm'>
          <Checkbox
            checked={superseded}
            onCheckedChange={(c) => setSuperseded(c === true)}
          />
          Show superseded
        </label>
      </div>
      <div className='grid max-h-52 gap-1 overflow-y-auto rounded-md border p-2 text-sm'>
        {shown.length === 0 ? (
          <span className='text-muted-foreground'>
            No documents. Upload them under Documents first.
          </span>
        ) : null}
        {shown.map((f) => (
          <label key={f.id} className='flex items-center gap-2'>
            <Checkbox
              checked={selected.includes(f.id)}
              onCheckedChange={(on) =>
                onChange(
                  on === true
                    ? [...selected, f.id]
                    : selected.filter((id) => id !== f.id)
                )
              }
            />
            <span className='flex-1 truncate'>{f.name}</span>
            <span className='text-xs text-muted-foreground'>
              rev {f.revision} · {f.category}
            </span>
            {f.is_latest ? null : <StatusBadge status='superseded' />}
          </label>
        ))}
      </div>
    </div>
  )
}

/** Contacts to tick; those without an email are marked, since they won't get the email. */
export function ContactPicker({
  selected,
  onChange,
  exclude = [],
}: {
  selected: number[]
  onChange: (ids: number[]) => void
  exclude?: number[]
}) {
  const { data: contacts = [] } = useContactOptions()
  const shown = contacts.filter((c) => !exclude.includes(c.id))
  return (
    <div className='grid max-h-44 grid-cols-2 gap-1 overflow-y-auto rounded-md border p-2 text-sm'>
      {shown.length === 0 ? (
        <span className='text-muted-foreground'>No contacts to add.</span>
      ) : null}
      {shown.map((c) => (
        <label key={c.id} className='flex items-center gap-1.5'>
          <Checkbox
            checked={selected.includes(c.id)}
            onCheckedChange={(on) =>
              onChange(
                on === true
                  ? [...selected, c.id]
                  : selected.filter((id) => id !== c.id)
              )
            }
          />
          <span className='truncate'>
            {c.name}
            {c.email ? null : (
              <span className='text-xs text-muted-foreground'> (no email)</span>
            )}
          </span>
        </label>
      ))}
    </div>
  )
}
