import { useState } from 'react'
import {
  Archive,
  FolderInput,
  GitMerge,
  Plus,
  Split,
  Trash2,
} from 'lucide-react'
import { api, unwrap } from '@/api/client'
import { can, useSession } from '@/lib/session'
import { Button } from '@/components/ui/button'
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
import { ConfirmDialog } from '@/components/confirm-dialog'
import { NativeSelect } from '@/components/native-select'
import { StatusBadge } from '@/components/records/status-badge'
import {
  type Level,
  type NodeUpdate,
  type TreeNode,
  schemaFields,
  useNode,
  useNodePath,
  useTreeWrite,
} from './api'
import { NodePicker, SchemaFieldsEditor } from './pickers'
import type { TermFn } from './terminology'

type Ctx = { projectId: number; levels: Level[]; term: TermFn }

/** Levels allowed directly under `parent` (or at the top, for `null`). */
function childLevels(levels: Level[], parent: TreeNode | null) {
  return levels.filter((lv) =>
    parent
      ? lv.allowed_parent_keys.includes(parent.level_key)
      : lv.allowed_parent_keys.length === 0 ||
        lv.allowed_parent_keys.includes('')
  )
}

export function AddNodeDialog({
  ctx,
  parent,
  onClose,
  onCreated,
}: {
  ctx: Ctx
  parent: TreeNode | null
  onClose: () => void
  onCreated: (node: TreeNode) => void
}) {
  const { term } = ctx
  const options = childLevels(ctx.levels, parent)
  const [levelKey, setLevelKey] = useState(options[0]?.key ?? '')
  const [code, setCode] = useState('')
  const [name, setName] = useState('')
  const create = useTreeWrite(ctx.projectId, () =>
    unwrap(
      api.POST('/api/v1/asset-tree/nodes/', {
        body: {
          project_id: ctx.projectId,
          level_key: levelKey,
          code: code.trim(),
          name: name.trim() || null,
          parent_id: parent?.id ?? null,
        },
      })
    )
  )
  const level = options.find((l) => l.key === levelKey)
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className='sm:max-w-md'>
        <DialogHeader>
          <DialogTitle>
            {parent ? `Add under ${parent.display_path}` : 'Add at the top'}
          </DialogTitle>
        </DialogHeader>
        {options.length === 0 ? (
          <p className='text-sm text-muted-foreground'>
            No level may sit here. Change the levels in Settings.
          </p>
        ) : (
          <form
            id='add-node'
            className='grid gap-3'
            onSubmit={(e) => {
              e.preventDefault()
              create.mutate(undefined, {
                onSuccess: (n) => {
                  onCreated(n as TreeNode)
                  onClose()
                },
              })
            }}
          >
            <div className='grid gap-1.5'>
              <Label htmlFor='add-level'>Level</Label>
              <NativeSelect
                id='add-level'
                options={options.map((l) => ({
                  value: l.key,
                  label: term(`level.${l.key}`),
                }))}
                value={levelKey}
                onChange={(e) => setLevelKey(e.target.value)}
              />
            </div>
            <div className='grid gap-1.5'>
              <Label htmlFor='add-code'>Code</Label>
              <Input
                id='add-code'
                required
                value={code}
                onChange={(e) => setCode(e.target.value)}
                placeholder={level?.code_pattern ?? ''}
              />
            </div>
            <div className='grid gap-1.5'>
              <Label htmlFor='add-name'>Name</Label>
              <Input
                id='add-name'
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </div>
          </form>
        )}
        <DialogFooter>
          <Button
            type='submit'
            form='add-node'
            disabled={!code.trim() || !levelKey || create.isPending}
          >
            Add {levelKey ? term(`level.${levelKey}`) : ''}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function MoveDialog({
  ctx,
  node,
  onClose,
}: {
  ctx: Ctx
  node: TreeNode
  onClose: () => void
}) {
  const [target, setTarget] = useState<TreeNode[]>([])
  const [toTop, setToTop] = useState(false)
  const level = ctx.levels.find((l) => l.key === node.level_key)
  const move = useTreeWrite(ctx.projectId, (parentId: number | null) =>
    unwrap(
      api.POST('/api/v1/asset-tree/nodes/{node_id}/move', {
        params: { path: { node_id: node.id } },
        body: { parent_id: parentId },
      })
    )
  )
  const allowed = level?.allowed_parent_keys ?? []
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className='sm:max-w-lg'>
        <DialogHeader>
          <DialogTitle>Move {node.display_path}</DialogTitle>
          <DialogDescription>
            Its subtree moves with it. A {ctx.term(`level.${node.level_key}`)}{' '}
            can sit under:{' '}
            {allowed.length
              ? allowed.map((k) => ctx.term(`level.${k}`)).join(', ')
              : 'nothing (top level only)'}
            .
          </DialogDescription>
        </DialogHeader>
        <NodePicker
          projectId={ctx.projectId}
          term={ctx.term}
          selected={target}
          onChange={(n) => {
            setTarget(n)
            setToTop(false)
          }}
          exclude={[node.id]}
          filter={(n) =>
            allowed.includes(n.level_key) && !n.path.startsWith(node.path)
          }
        />
        {allowed.length === 0 || allowed.includes('') ? (
          <label className='flex items-center gap-2 text-sm'>
            <input
              type='checkbox'
              checked={toTop}
              onChange={(e) => {
                setToTop(e.target.checked)
                setTarget([])
              }}
            />
            Move to the top level
          </label>
        ) : null}
        <DialogFooter>
          <Button
            disabled={(!target.length && !toTop) || move.isPending}
            onClick={() =>
              move.mutate(toTop ? null : target[0].id, { onSuccess: onClose })
            }
          >
            Move
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function SplitDialog({
  ctx,
  node,
  onClose,
}: {
  ctx: Ctx
  node: TreeNode
  onClose: () => void
}) {
  const [parts, setParts] = useState([
    { code: `${node.code}a`, name: '' },
    { code: `${node.code}b`, name: '' },
  ])
  const split = useTreeWrite(ctx.projectId, () =>
    unwrap(
      api.POST('/api/v1/asset-tree/nodes/{node_id}/split', {
        params: { path: { node_id: node.id } },
        body: {
          parts: parts.map((p) => ({
            code: p.code.trim(),
            name: p.name.trim() || null,
          })),
        },
      })
    )
  )
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className='sm:max-w-lg'>
        <DialogHeader>
          <DialogTitle>Split {node.display_path}</DialogTitle>
          <DialogDescription>
            It is retired and superseded by the new{' '}
            {ctx.term(`level.${node.level_key}`, 2)}; records on it roll up to
            them through the lineage.
          </DialogDescription>
        </DialogHeader>
        <div className='grid gap-2'>
          {parts.map((p, i) => (
            <div key={i} className='grid grid-cols-[1fr_2fr_auto] gap-2'>
              <Input
                aria-label={`Part ${i + 1} code`}
                value={p.code}
                onChange={(e) =>
                  setParts(
                    parts.map((x, j) =>
                      j === i ? { ...x, code: e.target.value } : x
                    )
                  )
                }
              />
              <Input
                aria-label={`Part ${i + 1} name`}
                placeholder='Name'
                value={p.name}
                onChange={(e) =>
                  setParts(
                    parts.map((x, j) =>
                      j === i ? { ...x, name: e.target.value } : x
                    )
                  )
                }
              />
              <Button
                variant='ghost'
                size='icon'
                aria-label='Remove part'
                disabled={parts.length <= 2}
                onClick={() => setParts(parts.filter((_, j) => j !== i))}
              >
                <Trash2 />
              </Button>
            </div>
          ))}
          <Button
            variant='outline'
            size='sm'
            className='w-fit'
            onClick={() => setParts([...parts, { code: '', name: '' }])}
          >
            <Plus /> Add part
          </Button>
        </div>
        <DialogFooter>
          <Button
            disabled={
              parts.some((p) => !p.code.trim()) ||
              split.isPending ||
              node.status === 'retired'
            }
            onClick={() => split.mutate(undefined, { onSuccess: onClose })}
          >
            Split
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function MergeDialog({
  ctx,
  node,
  onClose,
}: {
  ctx: Ctx
  node: TreeNode
  onClose: () => void
}) {
  const [sources, setSources] = useState<TreeNode[]>([])
  const merge = useTreeWrite(ctx.projectId, () =>
    unwrap(
      api.POST('/api/v1/asset-tree/nodes/{node_id}/merge', {
        params: { path: { node_id: node.id } },
        body: { source_ids: sources.map((s) => s.id) },
      })
    )
  )
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className='sm:max-w-lg'>
        <DialogHeader>
          <DialogTitle>Merge into {node.display_path}</DialogTitle>
          <DialogDescription>
            The chosen {ctx.term(`level.${node.level_key}`, 2)} are retired and
            superseded by this one.
          </DialogDescription>
        </DialogHeader>
        <NodePicker
          projectId={ctx.projectId}
          term={ctx.term}
          multiple
          selected={sources}
          onChange={setSources}
          exclude={[node.id]}
          filter={(n) => n.level_key === node.level_key}
        />
        <DialogFooter>
          <Button
            disabled={!sources.length || merge.isPending}
            onClick={() => merge.mutate(undefined, { onSuccess: onClose })}
          >
            Merge {sources.length || ''}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function RetireDialog({
  ctx,
  node,
  onClose,
}: {
  ctx: Ctx
  node: TreeNode
  onClose: () => void
}) {
  const [successors, setSuccessors] = useState<TreeNode[]>([])
  const retire = useTreeWrite(ctx.projectId, () =>
    unwrap(
      api.POST('/api/v1/asset-tree/nodes/{node_id}/retire', {
        params: { path: { node_id: node.id } },
        body: { superseded_by: successors.map((s) => s.id) },
      })
    )
  )
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className='sm:max-w-lg'>
        <DialogHeader>
          <DialogTitle>Retire {node.display_path}</DialogTitle>
          <DialogDescription>
            Nothing new can be added under a retired node. Optionally name what
            supersedes it.
          </DialogDescription>
        </DialogHeader>
        <NodePicker
          projectId={ctx.projectId}
          term={ctx.term}
          multiple
          selected={successors}
          onChange={setSuccessors}
          exclude={[node.id]}
        />
        <DialogFooter>
          <Button
            variant='destructive'
            disabled={retire.isPending}
            onClick={() => retire.mutate(undefined, { onSuccess: onClose })}
          >
            Retire
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

const TEXT_FIELDS = [
  ['name', 'Name'],
  ['discipline_code', 'Discipline'],
  ['wbs_code', 'WBS code'],
] as const
const PROGRESS_FIELDS = [
  ['planned_start', 'Planned start', 'date'],
  ['planned_finish', 'Planned finish', 'date'],
  ['budget_qty', 'Budget qty', 'number'],
  ['uom', 'Unit', 'text'],
  ['budget_hours', 'Budget hours', 'number'],
  ['earned_qty', 'Earned qty', 'number'],
] as const

function NodeForm({
  ctx,
  node,
  level,
}: {
  ctx: Ctx
  node: TreeNode
  level: Level | undefined
}) {
  const session = useSession()
  const editable =
    can(session, 'asset_tree.update') && node.status !== 'retired'
  const progress =
    level?.roles.includes('progress_unit') ||
    level?.roles.includes('schedule_link')
  const initial = () => {
    const v: Record<string, string> = {}
    for (const [k] of TEXT_FIELDS) v[k] = node[k] ?? ''
    for (const [k] of PROGRESS_FIELDS)
      v[k] = node[k] == null ? '' : String(node[k])
    return v
  }
  const [values, setValues] = useState(initial)
  const [custom, setCustom] = useState<Record<string, unknown>>(
    node.custom_fields ?? {}
  )
  const save = useTreeWrite(ctx.projectId, (body: NodeUpdate) =>
    unwrap(
      api.PATCH('/api/v1/asset-tree/nodes/{node_id}', {
        params: { path: { node_id: node.id } },
        body,
      })
    )
  )
  const fields = schemaFields(level?.field_schema)
  const submit = () => {
    const body: Record<string, unknown> = { custom_fields: custom }
    for (const [k, v] of Object.entries(values)) {
      const was = initial()[k]
      if (v === was) continue
      const kind = PROGRESS_FIELDS.find((f) => f[0] === k)?.[2]
      body[k] = v === '' ? null : kind === 'number' ? Number(v) : v
    }
    save.mutate(body as NodeUpdate)
  }
  const input = (k: string, label: string, type = 'text') => (
    <div key={k} className='grid gap-1'>
      <Label htmlFor={`node-${k}`}>{label}</Label>
      <Input
        id={`node-${k}`}
        type={type}
        step='any'
        readOnly={!editable}
        value={values[k]}
        onChange={(e) => setValues({ ...values, [k]: e.target.value })}
      />
    </div>
  )
  return (
    <form
      className='grid gap-3'
      onSubmit={(e) => {
        e.preventDefault()
        submit()
      }}
    >
      <div className='grid grid-cols-2 gap-3'>
        {TEXT_FIELDS.map(([k, label]) => input(k, label))}
      </div>
      {progress ? (
        <div className='grid grid-cols-3 gap-3'>
          {PROGRESS_FIELDS.map(([k, label, type]) => input(k, label, type))}
        </div>
      ) : null}
      {fields.length ? (
        <>
          <h4 className='text-sm font-medium'>
            {ctx.term(`level.${node.level_key}`)} fields
          </h4>
          <SchemaFieldsEditor
            idPrefix={`node-${node.id}`}
            fields={fields}
            value={custom}
            onChange={setCustom}
            readOnly={!editable}
          />
        </>
      ) : null}
      {editable ? (
        <Button
          type='submit'
          size='sm'
          className='w-fit'
          disabled={save.isPending}
        >
          Save
        </Button>
      ) : null}
    </form>
  )
}

function Lineage({
  label,
  ids,
  onSelect,
}: {
  label: string
  ids: number[]
  onSelect: (id: number) => void
}) {
  if (!ids.length) return null
  return (
    <div className='flex flex-wrap items-center gap-1 text-sm'>
      <span className='text-muted-foreground'>{label}:</span>
      {ids.map((id) => (
        <LineageLink key={id} id={id} onSelect={onSelect} />
      ))}
    </div>
  )
}

function LineageLink({
  id,
  onSelect,
}: {
  id: number
  onSelect: (id: number) => void
}) {
  const { data } = useNode(id)
  return (
    <button
      type='button'
      className='text-primary underline-offset-2 hover:underline'
      onClick={() => onSelect(id)}
    >
      {data?.display_path ?? `#${id}`}
    </button>
  )
}

type Dialogs = 'add' | 'move' | 'split' | 'merge' | 'retire' | 'delete' | null

/** The selected node: breadcrumb, fields, lineage and the restructure actions. */
export function NodePanel({
  ctx,
  nodeId,
  onSelect,
}: {
  ctx: Ctx
  nodeId: number
  onSelect: (id: number | null) => void
}) {
  const session = useSession()
  const { data: node } = useNode(nodeId)
  const { data: path = [] } = useNodePath(nodeId)
  const [dialog, setDialog] = useState<Dialogs>(null)
  const remove = useTreeWrite(ctx.projectId, () =>
    unwrap(
      api.DELETE('/api/v1/asset-tree/nodes/{node_id}', {
        params: { path: { node_id: nodeId } },
      })
    )
  )
  if (!node) return null
  const level = ctx.levels.find((l) => l.key === node.level_key)
  const retired = node.status === 'retired'
  const canUpdate = can(session, 'asset_tree.update')
  const close = () => setDialog(null)
  return (
    <div className='grid gap-4'>
      <nav aria-label='Breadcrumb' className='flex flex-wrap gap-1 text-sm'>
        {path.map((p, i) => (
          <span key={p.id} className='flex items-center gap-1'>
            {i ? <span className='text-muted-foreground'>/</span> : null}
            <button
              type='button'
              className={
                p.id === node.id
                  ? 'font-medium'
                  : 'text-muted-foreground hover:underline'
              }
              onClick={() => onSelect(p.id)}
            >
              <span className='text-xs'>
                {ctx.term(`level.${p.level_key}`)}
              </span>{' '}
              {p.code}
            </button>
          </span>
        ))}
      </nav>
      <div className='flex flex-wrap items-start justify-between gap-2'>
        <div>
          <h3 className='text-lg font-semibold'>
            {ctx.term(`level.${node.level_key}`)} {node.code}
            {node.name ? (
              <span className='font-normal text-muted-foreground'>
                {' '}
                — {node.name}
              </span>
            ) : null}
          </h3>
          <div className='flex flex-wrap gap-1.5 pt-1'>
            <StatusBadge status={node.status} />
            {(level?.roles ?? []).map((r) => (
              <span
                key={r}
                className='rounded bg-muted px-1.5 py-0.5 text-xs text-muted-foreground'
              >
                {r.replace(/_/g, ' ')}
              </span>
            ))}
            {node.display_code ? (
              <span className='font-mono text-xs'>{node.display_code}</span>
            ) : null}
          </div>
        </div>
        <div className='flex flex-wrap gap-1'>
          {can(session, 'asset_tree.create') && !retired ? (
            <Button size='sm' onClick={() => setDialog('add')}>
              <Plus /> Add under
            </Button>
          ) : null}
          {canUpdate && !retired ? (
            <>
              <Button
                size='sm'
                variant='outline'
                onClick={() => setDialog('move')}
              >
                <FolderInput /> Move
              </Button>
              <Button
                size='sm'
                variant='outline'
                onClick={() => setDialog('split')}
              >
                <Split /> Split
              </Button>
              <Button
                size='sm'
                variant='outline'
                onClick={() => setDialog('merge')}
              >
                <GitMerge /> Merge
              </Button>
              <Button
                size='sm'
                variant='outline'
                onClick={() => setDialog('retire')}
              >
                <Archive /> Retire
              </Button>
            </>
          ) : null}
          {can(session, 'asset_tree.delete') &&
          !node.child_count &&
          !node.item_count ? (
            <Button
              size='sm'
              variant='ghost'
              aria-label='Delete'
              onClick={() => setDialog('delete')}
            >
              <Trash2 />
            </Button>
          ) : null}
        </div>
      </div>
      <div className='grid gap-1'>
        <Lineage
          label='Derived from'
          ids={node.derived_from}
          onSelect={onSelect}
        />
        <Lineage
          label='Superseded by'
          ids={node.superseded_by}
          onSelect={onSelect}
        />
      </div>
      <NodeForm
        key={JSON.stringify(node)}
        ctx={ctx}
        node={node}
        level={level}
      />
      {dialog === 'add' ? (
        <AddNodeDialog
          ctx={ctx}
          parent={node}
          onClose={close}
          onCreated={(n) => onSelect(n.id)}
        />
      ) : null}
      {dialog === 'move' ? (
        <MoveDialog ctx={ctx} node={node} onClose={close} />
      ) : null}
      {dialog === 'split' ? (
        <SplitDialog ctx={ctx} node={node} onClose={close} />
      ) : null}
      {dialog === 'merge' ? (
        <MergeDialog ctx={ctx} node={node} onClose={close} />
      ) : null}
      {dialog === 'retire' ? (
        <RetireDialog ctx={ctx} node={node} onClose={close} />
      ) : null}
      <ConfirmDialog
        open={dialog === 'delete'}
        onOpenChange={(o) => !o && close()}
        title={`Delete ${node.display_path}?`}
        desc='Only an empty node can be deleted. This cannot be undone.'
        destructive
        confirmText='Delete'
        handleConfirm={() =>
          remove.mutate(undefined, {
            onSuccess: () => {
              close()
              onSelect(node.parent_id)
            },
          })
        }
      />
    </div>
  )
}
