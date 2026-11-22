/** Breakdown settings: starting packs, levels, item types and terminology. Needs `asset_tree.configure`. */
import { useState } from 'react'
import { Plus, RotateCcw } from 'lucide-react'
import { toast } from 'sonner'
import { api, unwrap } from '@/api/client'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Textarea } from '@/components/ui/textarea'
import { NativeSelect } from '@/components/native-select'
import {
  type ItemType,
  type Level,
  type LevelIn,
  ROLES,
  UNIQUENESS,
  useItemTypes,
  useLevels,
  usePacks,
  useTermList,
  useTreeWrite,
} from './api'
import type { TermFn } from './terminology'

function parseJson(text: string): Record<string, unknown> | null {
  if (!text.trim()) return {}
  try {
    const v = JSON.parse(text)
    return v && typeof v === 'object' && !Array.isArray(v) ? v : null
  } catch {
    return null
  }
}

function Packs({ projectId }: { projectId: number }) {
  const { data = [] } = usePacks()
  const apply = useTreeWrite(projectId, (key: string) =>
    unwrap(
      api.POST('/api/v1/asset-tree/packs/{key}/apply', {
        params: { path: { key }, query: { project_id: projectId } },
      })
    )
  )
  return (
    <div className='grid gap-2'>
      <p className='text-sm text-muted-foreground'>
        A pack adds its levels, item types and terminology where the project
        doesn't have them yet. Applying again changes nothing; existing levels
        are never rewritten.
      </p>
      {data.map((p) => (
        <div
          key={p.key}
          className='flex items-center gap-3 rounded-md border p-2 text-sm'
        >
          <div className='grid flex-1'>
            <span className='font-medium'>{p.title}</span>
            <span className='text-xs text-muted-foreground'>
              {p.levels.join(' → ')}
            </span>
          </div>
          <Button
            size='sm'
            disabled={apply.isPending}
            onClick={() =>
              apply.mutate(p.key, {
                onSuccess: (r) => {
                  const res = r as Record<string, number>
                  toast.success(
                    `${res.levels_added} levels and ${res.item_types_added} item types added`
                  )
                },
              })
            }
          >
            Apply
          </Button>
        </div>
      ))}
    </div>
  )
}

const blankLevel = (depth: number): LevelIn => ({
  key: '',
  label: '',
  label_plural: '',
  depth,
  allowed_parent_keys: [],
  roles: [],
  code_pattern: null,
  code_uniqueness: 'per_parent',
  display_code_template: null,
  field_schema: {},
})

function LevelEditor({
  projectId,
  level,
  levels,
  onDone,
}: {
  projectId: number
  level: Level | null
  levels: Level[]
  onDone: () => void
}) {
  const [v, setV] = useState<LevelIn>(() =>
    level
      ? {
          key: level.key,
          label: level.label,
          label_plural: level.label_plural,
          depth: level.depth,
          allowed_parent_keys: level.allowed_parent_keys,
          roles: level.roles as LevelIn['roles'],
          code_pattern: level.code_pattern,
          code_uniqueness: level.code_uniqueness as LevelIn['code_uniqueness'],
          display_code_template: level.display_code_template,
          field_schema: level.field_schema,
        }
      : blankLevel(levels.length)
  )
  const [schema, setSchema] = useState(
    JSON.stringify(level?.field_schema ?? {}, null, 2)
  )
  const parsed = parseJson(schema)
  const save = useTreeWrite(projectId, (body: LevelIn) =>
    level
      ? unwrap(
          api.PATCH('/api/v1/asset-tree/levels/{level_id}', {
            params: { path: { level_id: level.id } },
            body,
          })
        )
      : unwrap(
          api.POST('/api/v1/asset-tree/levels', {
            params: { query: { project_id: projectId } },
            body,
          })
        )
  )
  const toggle = (list: string[], item: string) =>
    list.includes(item) ? list.filter((x) => x !== item) : [...list, item]
  const text = (key: keyof LevelIn, label: string, hint?: string) => (
    <div className='grid gap-1'>
      <Label htmlFor={`lvl-${key}`}>{label}</Label>
      <Input
        id={`lvl-${key}`}
        readOnly={key === 'key' && Boolean(level)}
        placeholder={hint}
        value={(v[key] as string | null) ?? ''}
        onChange={(e) =>
          setV({
            ...v,
            [key]:
              key === 'depth'
                ? Number(e.target.value)
                : e.target.value ||
                  (key === 'code_pattern' || key === 'display_code_template'
                    ? null
                    : ''),
          })
        }
      />
    </div>
  )
  return (
    <form
      className='grid gap-3 rounded-md border p-3'
      onSubmit={(e) => {
        e.preventDefault()
        if (parsed)
          save.mutate({ ...v, field_schema: parsed }, { onSuccess: onDone })
      }}
    >
      <div className='grid grid-cols-2 gap-3 sm:grid-cols-4'>
        {text('key', 'Key', 'e.g. rsw')}
        {text('label', 'Label', 'RSW')}
        {text('label_plural', 'Plural', 'RSWs')}
        {text('depth', 'Depth')}
        {text('code_pattern', 'Code pattern (regex)', '^\\d+\\.\\d+$')}
        {text('display_code_template', 'Display template', '{asset} / {rsw}')}
        <div className='grid gap-1'>
          <Label htmlFor='lvl-unique'>Codes unique</Label>
          <NativeSelect
            id='lvl-unique'
            values={UNIQUENESS}
            value={v.code_uniqueness ?? 'per_parent'}
            onChange={(e) =>
              setV({
                ...v,
                code_uniqueness: e.target.value as LevelIn['code_uniqueness'],
              })
            }
          />
        </div>
      </div>
      <fieldset className='grid gap-1'>
        <legend className='text-sm font-medium'>Roles</legend>
        <div className='flex flex-wrap gap-3 text-sm'>
          {ROLES.map((r) => (
            <label key={r} className='flex items-center gap-1.5'>
              <Checkbox
                checked={(v.roles ?? []).includes(r)}
                onCheckedChange={() =>
                  setV({
                    ...v,
                    roles: toggle(v.roles ?? [], r) as LevelIn['roles'],
                  })
                }
              />
              {r.replace(/_/g, ' ')}
            </label>
          ))}
        </div>
      </fieldset>
      <fieldset className='grid gap-1'>
        <legend className='text-sm font-medium'>
          May sit under (none: top level only)
        </legend>
        <div className='flex flex-wrap gap-3 text-sm'>
          {levels
            .filter((l) => l.key !== v.key)
            .map((l) => (
              <label key={l.key} className='flex items-center gap-1.5'>
                <Checkbox
                  checked={(v.allowed_parent_keys ?? []).includes(l.key)}
                  onCheckedChange={() =>
                    setV({
                      ...v,
                      allowed_parent_keys: toggle(
                        v.allowed_parent_keys ?? [],
                        l.key
                      ),
                    })
                  }
                />
                {l.label}
              </label>
            ))}
          <label className='flex items-center gap-1.5'>
            <Checkbox
              checked={(v.allowed_parent_keys ?? []).includes('')}
              onCheckedChange={() =>
                setV({
                  ...v,
                  allowed_parent_keys: toggle(v.allowed_parent_keys ?? [], ''),
                })
              }
            />
            also at the top
          </label>
        </div>
      </fieldset>
      <div className='grid gap-1'>
        <Label htmlFor='lvl-schema'>Custom fields (JSONSchema)</Label>
        <Textarea
          id='lvl-schema'
          rows={5}
          className='font-mono text-xs'
          value={schema}
          onChange={(e) => setSchema(e.target.value)}
          placeholder='{"properties": {"priority": {"type": "string", "enum": ["P1", "P2"]}}}'
        />
        {!parsed ? (
          <p className='text-xs text-destructive'>Not valid JSON.</p>
        ) : null}
      </div>
      <div className='flex gap-2'>
        <Button
          type='submit'
          size='sm'
          disabled={
            !v.key || !v.label || !v.label_plural || !parsed || save.isPending
          }
        >
          Save level
        </Button>
        <Button type='button' size='sm' variant='ghost' onClick={onDone}>
          Cancel
        </Button>
      </div>
    </form>
  )
}

function Levels({ projectId }: { projectId: number }) {
  const { data: levels = [] } = useLevels(projectId)
  const [editing, setEditing] = useState<Level | 'new' | null>(null)
  return (
    <div className='grid gap-2'>
      <p className='text-sm text-muted-foreground'>
        Rules bind to a level's roles, never its name. A level's key never
        changes once nodes use it.
      </p>
      <ul className='grid gap-1 text-sm'>
        {levels.map((l) => (
          <li key={l.id}>
            <button
              type='button'
              className='flex w-full items-center gap-2 rounded-md border px-2 py-1 text-start hover:bg-muted'
              onClick={() => setEditing(l)}
            >
              <span className='w-6 text-muted-foreground'>{l.depth}</span>
              <span className='font-medium'>{l.label}</span>
              <span className='font-mono text-xs text-muted-foreground'>
                {l.key}
              </span>
              <span className='ms-auto truncate text-xs text-muted-foreground'>
                {l.roles.join(', ')}
              </span>
            </button>
          </li>
        ))}
      </ul>
      {editing ? (
        <LevelEditor
          key={editing === 'new' ? 'new' : editing.id}
          projectId={projectId}
          level={editing === 'new' ? null : editing}
          levels={levels}
          onDone={() => setEditing(null)}
        />
      ) : (
        <Button
          size='sm'
          variant='outline'
          className='w-fit'
          onClick={() => setEditing('new')}
        >
          <Plus /> Add level
        </Button>
      )}
    </div>
  )
}

function ItemTypeEditor({
  projectId,
  type,
  onDone,
}: {
  projectId: number
  type: ItemType | null
  onDone: () => void
}) {
  const [key, setKey] = useState(type?.key ?? '')
  const [name, setName] = useState(type?.name ?? '')
  const [inspectable, setInspectable] = useState(type?.inspectable ?? true)
  const [schema, setSchema] = useState(
    JSON.stringify(type?.field_schema ?? {}, null, 2)
  )
  const parsed = parseJson(schema)
  const save = useTreeWrite(projectId, () =>
    unwrap(
      api.PUT('/api/v1/asset-tree/item-types/{key}', {
        params: { path: { key }, query: { project_id: projectId } },
        body: { key, name, inspectable, field_schema: parsed ?? {} },
      })
    )
  )
  return (
    <form
      className='grid gap-3 rounded-md border p-3'
      onSubmit={(e) => {
        e.preventDefault()
        save.mutate(undefined, { onSuccess: onDone })
      }}
    >
      <div className='grid grid-cols-2 gap-3'>
        <div className='grid gap-1'>
          <Label htmlFor='type-key'>Key</Label>
          <Input
            id='type-key'
            readOnly={Boolean(type)}
            value={key}
            onChange={(e) => setKey(e.target.value)}
            placeholder='e.g. pipe_spool'
          />
        </div>
        <div className='grid gap-1'>
          <Label htmlFor='type-name'>Name</Label>
          <Input
            id='type-name'
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </div>
      </div>
      <label className='flex items-center gap-2 text-sm'>
        <Checkbox
          checked={inspectable}
          onCheckedChange={(c) => setInspectable(c === true)}
        />
        Inspectable
      </label>
      <div className='grid gap-1'>
        <Label htmlFor='type-schema'>
          Fields (JSONSchema){type ? ` — revision ${type.revision}` : ''}
        </Label>
        <Textarea
          id='type-schema'
          rows={6}
          className='font-mono text-xs'
          value={schema}
          onChange={(e) => setSchema(e.target.value)}
        />
        <p className='text-xs text-muted-foreground'>
          Changing the fields makes a new revision; existing items keep theirs.
        </p>
        {!parsed ? (
          <p className='text-xs text-destructive'>Not valid JSON.</p>
        ) : null}
      </div>
      <div className='flex gap-2'>
        <Button
          type='submit'
          size='sm'
          disabled={
            !/^[a-z][a-z0-9_]*$/.test(key) || !name || !parsed || save.isPending
          }
        >
          Save
        </Button>
        <Button type='button' size='sm' variant='ghost' onClick={onDone}>
          Cancel
        </Button>
      </div>
    </form>
  )
}

function ItemTypes({ projectId }: { projectId: number }) {
  const { data: types = [] } = useItemTypes(projectId)
  const [editing, setEditing] = useState<ItemType | 'new' | null>(null)
  return (
    <div className='grid gap-2'>
      <ul className='grid gap-1 text-sm'>
        {types.map((t) => (
          <li key={t.id}>
            <button
              type='button'
              className='flex w-full items-center gap-2 rounded-md border px-2 py-1 text-start hover:bg-muted'
              onClick={() => setEditing(t)}
            >
              <span className='font-medium'>{t.name}</span>
              <span className='font-mono text-xs text-muted-foreground'>
                {t.key}
              </span>
              <span className='ms-auto text-xs text-muted-foreground'>
                rev. {t.revision}
              </span>
            </button>
          </li>
        ))}
      </ul>
      {editing ? (
        <ItemTypeEditor
          key={editing === 'new' ? 'new' : editing.id}
          projectId={projectId}
          type={editing === 'new' ? null : editing}
          onDone={() => setEditing(null)}
        />
      ) : (
        <Button
          size='sm'
          variant='outline'
          className='w-fit'
          onClick={() => setEditing('new')}
        >
          <Plus /> Add item type
        </Button>
      )}
    </div>
  )
}

function Terminology({ projectId }: { projectId: number }) {
  const { data: terms = [] } = useTermList(projectId)
  const [edits, setEdits] = useState<
    Record<string, { one: string; other: string } | null>
  >({})
  const save = useTreeWrite(projectId, () =>
    unwrap(
      api.PUT('/api/v1/asset-tree/terminology', {
        params: { query: { project_id: projectId } },
        body: { terms: edits },
      })
    )
  )
  const value = (key: string, form: 'one' | 'other', fallback: string) =>
    edits[key] === null ? '' : (edits[key]?.[form] ?? fallback)
  return (
    <div className='grid gap-2'>
      <p className='text-sm text-muted-foreground'>
        What this project calls its levels and things. Screens, columns and
        breadcrumbs use these words.
      </p>
      <div className='max-h-[50vh] overflow-y-auto rounded-md border'>
        <table className='w-full text-sm'>
          <thead className='sticky top-0 bg-background'>
            <tr className='text-start text-xs text-muted-foreground'>
              <th className='p-1 text-start'>Key</th>
              <th className='p-1 text-start'>One</th>
              <th className='p-1 text-start'>Many</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {terms
              .filter((t) => !t.key.startsWith('role.'))
              .map((t) => (
                <tr key={t.key} className='border-t'>
                  <td className='p-1 font-mono text-xs'>{t.key}</td>
                  {(['one', 'other'] as const).map((form) => (
                    <td key={form} className='p-1'>
                      <Input
                        aria-label={`${t.key} ${form}`}
                        className='h-7'
                        value={value(t.key, form, t[form])}
                        onChange={(e) =>
                          setEdits({
                            ...edits,
                            [t.key]: {
                              one: value(t.key, 'one', t.one),
                              other: value(t.key, 'other', t.other),
                              [form]: e.target.value,
                            },
                          })
                        }
                      />
                    </td>
                  ))}
                  <td className='p-1'>
                    {t.source === 'project' ? (
                      <Button
                        size='icon'
                        variant='ghost'
                        className='size-7'
                        aria-label={`Reset ${t.key}`}
                        onClick={() => setEdits({ ...edits, [t.key]: null })}
                      >
                        <RotateCcw />
                      </Button>
                    ) : null}
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>
      <Button
        size='sm'
        className='w-fit'
        disabled={!Object.keys(edits).length || save.isPending}
        onClick={() =>
          save.mutate(undefined, {
            onSuccess: () => {
              setEdits({})
              toast.success('Terminology saved')
            },
          })
        }
      >
        Save terminology
      </Button>
    </div>
  )
}

export function SettingsDialog({
  projectId,
  term,
  onClose,
}: {
  projectId: number
  term: TermFn
  onClose: () => void
}) {
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className='max-h-[90vh] overflow-y-auto sm:max-w-3xl'>
        <DialogHeader>
          <DialogTitle>Breakdown settings</DialogTitle>
          <DialogDescription>
            Levels, {term('noun.item_type', 2).toLowerCase()} and the words this
            project uses.
          </DialogDescription>
        </DialogHeader>
        <Tabs defaultValue='levels'>
          <TabsList>
            <TabsTrigger value='packs'>Starting packs</TabsTrigger>
            <TabsTrigger value='levels'>Levels</TabsTrigger>
            <TabsTrigger value='types'>{term('noun.item_type', 2)}</TabsTrigger>
            <TabsTrigger value='terms'>Terminology</TabsTrigger>
          </TabsList>
          <TabsContent value='packs'>
            <Packs projectId={projectId} />
          </TabsContent>
          <TabsContent value='levels'>
            <Levels projectId={projectId} />
          </TabsContent>
          <TabsContent value='types'>
            <ItemTypes projectId={projectId} />
          </TabsContent>
          <TabsContent value='terms'>
            <Terminology projectId={projectId} />
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  )
}
