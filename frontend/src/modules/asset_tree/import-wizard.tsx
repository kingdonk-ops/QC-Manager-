/**
 * The breakdown ingestion wizard: upload a spreadsheet, map its columns to levels, node fields, custom fields
 * and items, dry-run it, then apply. A mapping can be saved as a versioned profile and reused next time.
 */
import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { Plus, Trash2 } from 'lucide-react'
import { toast } from 'sonner'
import { handleServerError } from '@/lib/handle-server-error'
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
import { NativeSelect } from '@/components/native-select'
import {
  IDENTIFIER_KINDS,
  type ImportMapping,
  type ImportPreview,
  type ImportReport,
  type Level,
  postForm,
  useItemTypes,
  useProfiles,
  useTreeWrite,
} from './api'
import type { TermFn } from './terminology'

const NODE_FIELDS: [string, string][] = [
  ['name', 'Name'],
  ['discipline_code', 'Discipline'],
  ['wbs_code', 'WBS code'],
  ['external_id', 'External id'],
  ['planned_start', 'Planned start'],
  ['planned_finish', 'Planned finish'],
  ['budget_qty', 'Budget qty'],
  ['uom', 'Unit'],
  ['budget_hours', 'Budget hours'],
  ['earned_qty', 'Earned qty'],
]
type Item = NonNullable<ImportMapping['item']>

const snake = (header: string) =>
  header
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '')
    .replace(/^(\d)/, '_$1') || 'field'

function ColumnSelect({
  id,
  columns,
  value,
  onChange,
  label,
}: {
  id?: string
  columns: string[]
  value: string | null | undefined
  onChange: (v: string | null) => void
  label?: string
}) {
  return (
    <NativeSelect
      id={id}
      aria-label={label}
      className='h-8'
      placeholder='— not imported —'
      options={columns.map((c) => ({ value: c, label: c }))}
      value={value ?? ''}
      onChange={(e) => onChange(e.target.value || null)}
    />
  )
}

function setKey<T extends Record<string, string>>(
  map: T | undefined,
  key: string,
  column: string | null
): T {
  const next = { ...(map ?? {}) } as Record<string, string>
  if (column) next[key] = column
  else delete next[key]
  return next as T
}

function CustomFieldRows({
  columns,
  value,
  onChange,
}: {
  columns: string[]
  value: Record<string, string>
  onChange: (v: Record<string, string>) => void
}) {
  const rows = Object.entries(value)
  const [path, setPath] = useState('')
  const [column, setColumn] = useState<string | null>(null)
  return (
    <div className='grid gap-1.5'>
      {rows.map(([p, c]) => (
        <div key={p} className='flex items-center gap-2 text-sm'>
          <span className='w-40 truncate font-mono text-xs'>{p}</span>
          <span className='text-muted-foreground'>←</span>
          <span className='flex-1 truncate'>{c}</span>
          <Button
            size='icon'
            variant='ghost'
            className='size-7'
            aria-label={`Remove ${p}`}
            onClick={() => onChange(setKey(value, p, null))}
          >
            <Trash2 />
          </Button>
        </div>
      ))}
      <div className='flex items-center gap-2'>
        <Input
          aria-label='Custom field path'
          className='h-8 w-40 font-mono text-xs'
          placeholder='path.in.fields'
          value={path}
          onChange={(e) => setPath(e.target.value)}
        />
        <ColumnSelect
          label='Custom field column'
          columns={columns}
          value={column}
          onChange={setColumn}
        />
        <Button
          size='sm'
          variant='outline'
          disabled={
            !/^[A-Za-z_][\w]*(\.[A-Za-z_][\w]*)*$/.test(path) || !column
          }
          onClick={() => {
            onChange({ ...value, [path]: column as string })
            setPath('')
            setColumn(null)
          }}
        >
          <Plus />
        </Button>
      </div>
    </div>
  )
}

function used(m: ImportMapping): Set<string> {
  const out = new Set<string>(
    [
      ...Object.values(m.level_columns ?? {}),
      ...Object.values(m.node_fields ?? {}),
      ...Object.values(m.custom_fields ?? {}),
      m.path_column,
      m.code_column,
      m.parent_column,
      m.level_column,
      m.item?.tag_column,
      m.item?.item_type_column,
      ...Object.values(m.item?.fields ?? {}),
      ...Object.values(m.item?.custom_fields ?? {}),
      ...Object.values(m.item?.identifiers ?? {}),
    ].filter(Boolean) as string[]
  )
  return out
}

function MappingEditor({
  projectId,
  columns,
  levels,
  term,
  m,
  set,
}: {
  projectId: number
  columns: string[]
  levels: Level[]
  term: TermFn
  m: ImportMapping
  set: (m: ImportMapping) => void
}) {
  const { data: types = [] } = useItemTypes(projectId)
  const mode = m.tree_mode ?? 'columns'
  const unmapped = columns.filter((c) => !used(m).has(c))
  const item = m.item ?? null
  const setItem = (patch: Partial<Item>) =>
    set({ ...m, item: { ...(item as Item), ...patch } })
  return (
    <div className='grid gap-4 text-sm'>
      <section className='grid gap-2'>
        <h4 className='font-medium'>Tree</h4>
        <div className='flex flex-wrap gap-4'>
          {(
            [
              ['columns', 'One column per level'],
              ['path', 'A path column'],
              ['parent_row', 'Parent on each row'],
            ] as const
          ).map(([value, label]) => (
            <label key={value} className='flex items-center gap-1.5'>
              <input
                type='radio'
                name='tree-mode'
                checked={mode === value}
                onChange={() => set({ ...m, tree_mode: value })}
              />
              {label}
            </label>
          ))}
        </div>
        {mode === 'columns' ? (
          <div className='grid grid-cols-2 gap-2 sm:grid-cols-3'>
            {levels.map((l) => (
              <div key={l.key} className='grid gap-1'>
                <Label htmlFor={`map-level-${l.key}`}>
                  {term(`level.${l.key}`)} code
                </Label>
                <ColumnSelect
                  id={`map-level-${l.key}`}
                  columns={columns}
                  value={m.level_columns?.[l.key]}
                  onChange={(c) =>
                    set({
                      ...m,
                      level_columns: setKey(m.level_columns, l.key, c),
                    })
                  }
                />
              </div>
            ))}
          </div>
        ) : mode === 'path' ? (
          <div className='grid gap-2'>
            <div className='grid grid-cols-[2fr_1fr] gap-2'>
              <div className='grid gap-1'>
                <Label htmlFor='map-path'>Path column</Label>
                <ColumnSelect
                  id='map-path'
                  columns={columns}
                  value={m.path_column}
                  onChange={(c) => set({ ...m, path_column: c })}
                />
              </div>
              <div className='grid gap-1'>
                <Label htmlFor='map-sep'>Separator</Label>
                <Input
                  id='map-sep'
                  className='h-8'
                  value={m.path_separator ?? '/'}
                  onChange={(e) =>
                    set({ ...m, path_separator: e.target.value })
                  }
                />
              </div>
            </div>
            <p className='text-muted-foreground'>
              Levels of the segments, in order:
            </p>
            <div className='flex flex-wrap gap-3'>
              {levels.map((l) => (
                <label key={l.key} className='flex items-center gap-1.5'>
                  <Checkbox
                    checked={(m.path_levels ?? []).includes(l.key)}
                    onCheckedChange={(c) => {
                      const keys = new Set(m.path_levels ?? [])
                      if (c === true) keys.add(l.key)
                      else keys.delete(l.key)
                      set({
                        ...m,
                        path_levels: levels
                          .map((x) => x.key)
                          .filter((k) => keys.has(k)),
                      })
                    }}
                  />
                  {term(`level.${l.key}`)}
                </label>
              ))}
            </div>
          </div>
        ) : (
          <div className='grid grid-cols-3 gap-2'>
            {(
              [
                ['code_column', 'Code'],
                ['parent_column', 'Parent code'],
                ['level_column', 'Level (key or name)'],
              ] as const
            ).map(([key, label]) => (
              <div key={key} className='grid gap-1'>
                <Label htmlFor={`map-${key}`}>{label}</Label>
                <ColumnSelect
                  id={`map-${key}`}
                  columns={columns}
                  value={m[key]}
                  onChange={(c) => set({ ...m, [key]: c })}
                />
              </div>
            ))}
          </div>
        )}
        <label className='flex items-center gap-1.5'>
          <Checkbox
            checked={m.split_multi_values ?? true}
            onCheckedChange={(c) =>
              set({ ...m, split_multi_values: c === true })
            }
          />
          Split cells like “101.1 and 101.3 ; 102” into several{' '}
          {term('noun.node', 2).toLowerCase()}
        </label>
      </section>

      <section className='grid gap-2'>
        <h4 className='font-medium'>Fields of each row's deepest node</h4>
        <div className='grid grid-cols-2 gap-2 sm:grid-cols-3'>
          {NODE_FIELDS.map(([key, label]) => (
            <div key={key} className='grid gap-1'>
              <Label htmlFor={`map-field-${key}`}>{label}</Label>
              <ColumnSelect
                id={`map-field-${key}`}
                columns={columns}
                value={m.node_fields?.[key as 'name']}
                onChange={(c) =>
                  set({ ...m, node_fields: setKey(m.node_fields, key, c) })
                }
              />
            </div>
          ))}
        </div>
        <h5 className='text-muted-foreground'>Custom fields</h5>
        <CustomFieldRows
          columns={columns}
          value={(m.custom_fields ?? {}) as Record<string, string>}
          onChange={(v) => set({ ...m, custom_fields: v })}
        />
        {unmapped.length ? (
          <Button
            size='sm'
            variant='ghost'
            className='w-fit'
            onClick={() =>
              set({
                ...m,
                custom_fields: {
                  ...(m.custom_fields ?? {}),
                  ...Object.fromEntries(unmapped.map((c) => [snake(c), c])),
                },
              })
            }
          >
            Keep the {unmapped.length} unmapped columns as custom fields
          </Button>
        ) : null}
      </section>

      <section className='grid gap-2'>
        <label className='flex items-center gap-1.5 font-medium'>
          <Checkbox
            checked={Boolean(item)}
            onCheckedChange={(c) =>
              set({
                ...m,
                item:
                  c === true
                    ? { tag_column: columns[0], item_type_key: types[0]?.key }
                    : null,
              })
            }
          />
          Rows also carry {term('noun.item', 2).toLowerCase()}
        </label>
        {item ? (
          <div className='grid gap-2'>
            <div className='grid grid-cols-2 gap-2 sm:grid-cols-3'>
              <div className='grid gap-1'>
                <Label htmlFor='map-tag'>Tag</Label>
                <ColumnSelect
                  id='map-tag'
                  columns={columns}
                  value={item.tag_column}
                  onChange={(c) => setItem({ tag_column: c ?? columns[0] })}
                />
              </div>
              <div className='grid gap-1'>
                <Label htmlFor='map-type'>{term('noun.item_type')}</Label>
                <NativeSelect
                  id='map-type'
                  className='h-8'
                  options={[
                    ...types.map((t) => ({
                      value: `key:${t.key}`,
                      label: t.name,
                    })),
                    ...columns.map((c) => ({
                      value: `col:${c}`,
                      label: `From column “${c}”`,
                    })),
                  ]}
                  value={
                    item.item_type_column
                      ? `col:${item.item_type_column}`
                      : `key:${item.item_type_key ?? ''}`
                  }
                  onChange={(e) => {
                    const [kind, v] = [
                      e.target.value.slice(0, 4),
                      e.target.value.slice(4),
                    ]
                    setItem(
                      kind === 'col:'
                        ? { item_type_column: v, item_type_key: null }
                        : { item_type_key: v, item_type_column: null }
                    )
                  }}
                />
              </div>
              {(
                [
                  ['spec_ref', 'Spec ref.'],
                  ['discipline', 'Discipline'],
                  ['notes', 'Notes'],
                ] as const
              ).map(([key, label]) => (
                <div key={key} className='grid gap-1'>
                  <Label htmlFor={`map-item-${key}`}>{label}</Label>
                  <ColumnSelect
                    id={`map-item-${key}`}
                    columns={columns}
                    value={item.fields?.[key]}
                    onChange={(c) =>
                      setItem({ fields: setKey(item.fields, key, c) })
                    }
                  />
                </div>
              ))}
              {IDENTIFIER_KINDS.map((kind) => (
                <div key={kind} className='grid gap-1'>
                  <Label htmlFor={`map-ident-${kind}`}>
                    {kind.toUpperCase()} code (read as text)
                  </Label>
                  <ColumnSelect
                    id={`map-ident-${kind}`}
                    columns={columns}
                    value={item.identifiers?.[kind]}
                    onChange={(c) =>
                      setItem({
                        identifiers: setKey(item.identifiers, kind, c),
                      })
                    }
                  />
                </div>
              ))}
            </div>
            <h5 className='text-muted-foreground'>
              {term('noun.item')} custom fields
            </h5>
            <CustomFieldRows
              columns={columns}
              value={(item.custom_fields ?? {}) as Record<string, string>}
              onChange={(v) => setItem({ custom_fields: v })}
            />
          </div>
        ) : null}
      </section>

      <section className='grid gap-1'>
        <Label htmlFor='map-mode'>
          Existing {term('noun.node', 2).toLowerCase()}
        </Label>
        <NativeSelect
          id='map-mode'
          className='h-8 w-80'
          options={[
            { value: 'upsert', label: 'Create new ones, update existing ones' },
            {
              value: 'create',
              label: 'Only create; leave existing ones alone',
            },
            {
              value: 'update',
              label: 'Only update; rows for unknown codes fail',
            },
          ]}
          value={m.update_mode ?? 'upsert'}
          onChange={(e) =>
            set({
              ...m,
              update_mode: e.target.value as ImportMapping['update_mode'],
            })
          }
        />
      </section>
    </div>
  )
}

function Report({ report }: { report: ImportReport }) {
  return (
    <div className='grid gap-2 rounded-md bg-muted/50 p-3 text-sm'>
      <p className='font-medium'>
        {report.dry_run ? 'Dry run (nothing written): ' : 'Imported: '}
        {report.nodes_created} created, {report.nodes_updated} updated,{' '}
        {report.nodes_unchanged} unchanged; {report.items_created} items
        created, {report.items_updated} updated; {report.skipped} rows skipped
        of {report.rows}.
      </p>
      {report.errors.length ? (
        <div>
          <p className='font-medium text-destructive'>
            {report.errors.length} errors
          </p>
          <ul className='max-h-32 overflow-y-auto text-xs'>
            {report.errors.slice(0, 200).map((e, i) => (
              <li key={i}>{e}</li>
            ))}
          </ul>
        </div>
      ) : null}
      {report.warnings.length ? (
        <div>
          <p className='font-medium text-amber-600'>
            {report.warnings.length} warnings
          </p>
          <ul className='max-h-32 overflow-y-auto text-xs'>
            {report.warnings.slice(0, 200).map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        </div>
      ) : null}
      {report.actions.length ? (
        <div className='max-h-48 overflow-y-auto rounded border bg-background'>
          <table className='w-full text-xs'>
            <tbody>
              {report.actions.slice(0, 300).map((a, i) => (
                <tr key={i} className='border-b'>
                  <td className='px-2 py-0.5 text-muted-foreground'>
                    Row {a.line}
                  </td>
                  <td className='px-2 py-0.5'>
                    {a.action === 'create' ? 'New' : 'Update'} {a.label}
                  </td>
                  <td className='px-2 py-0.5'>{a.display}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  )
}

export function ImportWizard({
  projectId,
  levels,
  term,
  onClose,
}: {
  projectId: number
  levels: Level[]
  term: TermFn
  onClose: () => void
}) {
  const { data: profiles = [] } = useProfiles(projectId)
  const [profileId, setProfileId] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<ImportPreview | null>(null)
  const [mapping, setMapping] = useState<ImportMapping | null>(null)
  const [report, setReport] = useState<ImportReport | null>(null)
  const [profileName, setProfileName] = useState('')
  const base = `/api/v1/asset-tree`

  const read = useMutation({
    mutationFn: ({ f, profile }: { f: File; profile: string }) => {
      const form = new FormData()
      form.set('file', f)
      if (profile) form.set('profile_id', profile)
      return postForm<ImportPreview>(
        `${base}/import/preview?project_id=${projectId}`,
        form
      )
    },
    onSuccess: (p) => {
      setPreview(p)
      setMapping(p.mapping)
      setReport(null)
    },
    onError: handleServerError,
  })
  const run = useTreeWrite(projectId, (dryRun: boolean) => {
    const form = new FormData()
    form.set('file', file as File)
    form.set('mapping', JSON.stringify(mapping))
    form.set('dry_run', String(dryRun))
    if (!dryRun && profileName.trim())
      form.set('save_profile_as', profileName.trim())
    return postForm<ImportReport>(
      `${base}/import?project_id=${projectId}`,
      form
    )
  })
  const go = (dryRun: boolean) =>
    run.mutate(dryRun, {
      onSuccess: (r) => {
        setReport(r)
        if (!r.dry_run)
          toast.success(
            `${r.nodes_created} created, ${r.nodes_updated} updated` +
              (r.profile
                ? `; profile “${r.profile.name}” v${r.profile.version} saved`
                : '')
          )
      },
    })
  const chosen = profiles.find((p) => String(p.id) === profileId)

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className='max-h-[90vh] overflow-y-auto sm:max-w-3xl'>
        <DialogHeader>
          <DialogTitle>Import the breakdown from Excel or CSV</DialogTitle>
          <DialogDescription>
            Codes are always read as text. Errors like #N/A become empty with a
            warning. Try a dry run first: it shows exactly what apply will do.
          </DialogDescription>
        </DialogHeader>
        <div className='flex flex-wrap items-end gap-3 text-sm'>
          <div className='grid gap-1'>
            <Label htmlFor='import-profile'>Mapping profile</Label>
            <NativeSelect
              id='import-profile'
              className='w-56'
              placeholder='Guess from the headers'
              options={profiles.map((p) => ({
                value: String(p.id),
                label: `${p.name} (v${p.version})`,
              }))}
              value={profileId}
              onChange={(e) => {
                setProfileId(e.target.value)
                if (file) read.mutate({ f: file, profile: e.target.value })
              }}
            />
          </div>
          <div className='grid gap-1'>
            <Label htmlFor='import-file'>File</Label>
            <Input
              id='import-file'
              type='file'
              accept='.xlsx,.xlsm,.csv,.txt'
              onChange={(e) => {
                const f = e.target.files?.[0] ?? null
                setFile(f)
                if (f) read.mutate({ f, profile: profileId })
              }}
            />
          </div>
        </div>
        {preview && mapping ? (
          <>
            <p className='text-sm text-muted-foreground'>
              {preview.rows} rows, {preview.columns.length} columns.
            </p>
            {preview.missing?.length ? (
              <p className='text-sm text-destructive'>
                This file has no column {preview.missing.join(', ')}.
              </p>
            ) : null}
            {preview.sample.length ? (
              <div className='max-h-40 overflow-auto rounded-md border'>
                <table className='w-full text-xs'>
                  <thead>
                    <tr>
                      {preview.columns.map((c) => (
                        <th
                          key={c}
                          className='border-b px-2 py-1 text-start font-medium whitespace-nowrap'
                        >
                          {c}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {preview.sample.map((row, i) => (
                      <tr key={i}>
                        {preview.columns.map((c) => (
                          <td
                            key={c}
                            className='border-b px-2 py-1 whitespace-nowrap'
                          >
                            {String(row[c] ?? '')}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : null}
            <MappingEditor
              projectId={projectId}
              columns={preview.columns}
              levels={levels}
              term={term}
              m={mapping}
              set={(m) => {
                setMapping(m)
                setReport(null)
              }}
            />
          </>
        ) : null}
        {report ? <Report report={report} /> : null}
        {preview ? (
          <div className='grid gap-1 text-sm'>
            <Label htmlFor='profile-name'>
              Save this mapping as a profile on import (optional)
            </Label>
            <Input
              id='profile-name'
              className='w-72'
              placeholder={chosen ? chosen.name : 'e.g. Client planning sheet'}
              value={profileName}
              onChange={(e) => setProfileName(e.target.value)}
            />
          </div>
        ) : null}
        <DialogFooter>
          <Button variant='outline' onClick={onClose}>
            {report && !report.dry_run ? 'Done' : 'Cancel'}
          </Button>
          <Button
            variant='outline'
            disabled={!preview || !mapping || run.isPending}
            onClick={() => go(true)}
          >
            Dry run
          </Button>
          <Button
            disabled={!preview || !mapping || run.isPending}
            onClick={() => go(false)}
          >
            Import
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
