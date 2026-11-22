import { useState } from 'react'
import { Plus, X } from 'lucide-react'
import { api, unwrap } from '@/api/client'
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
import { NativeSelect } from '@/components/native-select'
import {
  COLLECTION_KINDS,
  type Collection,
  type TreeNode,
  useCollections,
  useNode,
  useTreeWrite,
} from './api'
import { NodePicker } from './pickers'
import type { TermFn } from './terminology'

const kindTerm = (term: TermFn, kind: string, count = 1) =>
  term(kind === 'other' ? 'noun.collection' : `noun.${kind}`, count)

function NewCollection({
  projectId,
  term,
  onClose,
}: {
  projectId: number
  term: TermFn
  onClose: () => void
}) {
  const [draft, setDraft] = useState({
    kind: 'job_pack',
    code: '',
    name: '',
    window_start: '',
    window_end: '',
  })
  const create = useTreeWrite(projectId, () =>
    unwrap(
      api.POST('/api/v1/asset-tree/collections/', {
        body: {
          project_id: projectId,
          kind: draft.kind as 'job_pack',
          code: draft.code.trim(),
          name: draft.name.trim(),
          window_start: draft.window_start || null,
          window_end: draft.window_end || null,
        },
      })
    )
  )
  const field = (key: keyof typeof draft, label: string, type = 'text') => (
    <div className='grid gap-1.5'>
      <Label htmlFor={`col-${key}`}>{label}</Label>
      <Input
        id={`col-${key}`}
        type={type}
        required={key === 'code' || key === 'name'}
        value={draft[key]}
        onChange={(e) => setDraft({ ...draft, [key]: e.target.value })}
      />
    </div>
  )
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className='sm:max-w-md'>
        <DialogHeader>
          <DialogTitle>New {term('noun.collection').toLowerCase()}</DialogTitle>
        </DialogHeader>
        <form
          id='new-collection'
          className='grid gap-3'
          onSubmit={(e) => {
            e.preventDefault()
            create.mutate(undefined, { onSuccess: onClose })
          }}
        >
          <div className='grid gap-1.5'>
            <Label htmlFor='col-kind'>Kind</Label>
            <NativeSelect
              id='col-kind'
              options={COLLECTION_KINDS.map((k) => ({
                value: k,
                label: kindTerm(term, k),
              }))}
              value={draft.kind}
              onChange={(e) => setDraft({ ...draft, kind: e.target.value })}
            />
          </div>
          <div className='grid grid-cols-2 gap-3'>
            {field('code', 'Code')}
            {field('name', 'Name')}
            {field('window_start', 'Window start', 'date')}
            {field('window_end', 'Window end', 'date')}
          </div>
        </form>
        <DialogFooter>
          <Button
            type='submit'
            form='new-collection'
            disabled={
              !draft.code.trim() || !draft.name.trim() || create.isPending
            }
          >
            Create
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function Member({
  id,
  onRemove,
  onSelect,
}: {
  id: number
  onRemove?: () => void
  onSelect: (id: number) => void
}) {
  const { data } = useNode(id)
  return (
    <li className='flex items-center gap-2 rounded-md border px-2 py-1 text-sm'>
      <button
        type='button'
        className='truncate text-start hover:underline'
        onClick={() => onSelect(id)}
      >
        {data?.display_path ?? `#${id}`}
      </button>
      {onRemove ? (
        <Button
          size='icon'
          variant='ghost'
          className='ms-auto size-6'
          aria-label='Remove from collection'
          onClick={onRemove}
        >
          <X />
        </Button>
      ) : null}
    </li>
  )
}

function Members({
  projectId,
  collection,
  selectedNode,
  term,
  onSelect,
}: {
  projectId: number
  collection: Collection
  selectedNode: TreeNode | null
  term: TermFn
  onSelect: (id: number) => void
}) {
  const session = useSession()
  const editable = can(session, 'asset_tree.update')
  const [picking, setPicking] = useState(false)
  const [picked, setPicked] = useState<TreeNode[]>([])
  const ids = collection.node_ids ?? []
  const save = useTreeWrite(projectId, (nodeIds: number[]) =>
    unwrap(
      api.PUT('/api/v1/asset-tree/collections/{collection_id}/members', {
        params: { path: { collection_id: collection.id } },
        body: { node_ids: nodeIds },
      })
    )
  )
  return (
    <div className='grid gap-2'>
      <div className='flex flex-wrap items-center gap-2'>
        <h4 className='font-medium'>
          {collection.code} — {collection.name}
        </h4>
        {collection.window_start || collection.window_end ? (
          <span className='text-xs text-muted-foreground'>
            {collection.window_start ?? '…'} → {collection.window_end ?? '…'}
          </span>
        ) : null}
        {editable ? (
          <div className='ms-auto flex gap-1'>
            {selectedNode && !ids.includes(selectedNode.id) ? (
              <Button
                size='sm'
                variant='outline'
                onClick={() => save.mutate([...ids, selectedNode.id])}
              >
                <Plus /> Add {selectedNode.code}
              </Button>
            ) : null}
            <Button
              size='sm'
              variant='outline'
              onClick={() => setPicking(true)}
            >
              Pick {term('noun.node', 2).toLowerCase()}…
            </Button>
          </div>
        ) : null}
      </div>
      <ul className='grid gap-1'>
        {ids.map((id) => (
          <Member
            key={id}
            id={id}
            onSelect={onSelect}
            onRemove={
              editable
                ? () => save.mutate(ids.filter((x) => x !== id))
                : undefined
            }
          />
        ))}
        {!ids.length ? (
          <li className='text-sm text-muted-foreground'>
            No members. Select a node in the tree and add it, or pick several.
          </li>
        ) : null}
      </ul>
      {picking ? (
        <Dialog open onOpenChange={(o) => !o && setPicking(false)}>
          <DialogContent className='sm:max-w-lg'>
            <DialogHeader>
              <DialogTitle>Add to {collection.code}</DialogTitle>
            </DialogHeader>
            <NodePicker
              projectId={projectId}
              term={term}
              multiple
              selected={picked}
              onChange={setPicked}
              exclude={ids}
            />
            <DialogFooter>
              <Button
                disabled={!picked.length || save.isPending}
                onClick={() =>
                  save.mutate([...ids, ...picked.map((p) => p.id)], {
                    onSuccess: () => {
                      setPicked([])
                      setPicking(false)
                    },
                  })
                }
              >
                Add {picked.length || ''}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      ) : null}
    </div>
  )
}

/** Job packs, shutdown windows, test packs: named sets of nodes that never change the tree. */
export function CollectionsTab({
  projectId,
  selectedNode,
  term,
  onSelect,
}: {
  projectId: number
  selectedNode: TreeNode | null
  term: TermFn
  onSelect: (id: number) => void
}) {
  const session = useSession()
  const { data = [] } = useCollections(projectId)
  const [openId, setOpenId] = useState<number | null>(null)
  const [creating, setCreating] = useState(false)
  const open = data.find((c) => c.id === openId) ?? null
  return (
    <div className='grid gap-4 md:grid-cols-[260px_1fr]'>
      <div className='grid content-start gap-2'>
        {can(session, 'asset_tree.create') ? (
          <Button size='sm' className='w-fit' onClick={() => setCreating(true)}>
            <Plus /> New {term('noun.collection').toLowerCase()}
          </Button>
        ) : null}
        {COLLECTION_KINDS.map((kind) => {
          const ofKind = data.filter((c) => c.kind === kind)
          if (!ofKind.length) return null
          return (
            <div key={kind} className='grid gap-1'>
              <h4 className='text-xs font-medium text-muted-foreground uppercase'>
                {kindTerm(term, kind, 2)}
              </h4>
              {ofKind.map((c) => (
                <button
                  key={c.id}
                  type='button'
                  onClick={() => setOpenId(c.id)}
                  className={cn(
                    'flex items-center gap-2 rounded-md px-2 py-1 text-start text-sm hover:bg-muted',
                    openId === c.id && 'bg-primary/10 font-medium'
                  )}
                >
                  <span className='font-mono'>{c.code}</span>
                  <span className='truncate text-muted-foreground'>
                    {c.name}
                  </span>
                  <span className='ms-auto text-xs text-muted-foreground'>
                    {c.node_ids?.length ?? 0}
                  </span>
                </button>
              ))}
            </div>
          )
        })}
        {!data.length ? (
          <p className='text-sm text-muted-foreground'>
            No {term('noun.collection', 2).toLowerCase()} yet.
          </p>
        ) : null}
      </div>
      {open ? (
        <Members
          key={open.id}
          projectId={projectId}
          collection={open}
          selectedNode={selectedNode}
          term={term}
          onSelect={onSelect}
        />
      ) : (
        <p className='text-sm text-muted-foreground'>
          Choose a {term('noun.collection').toLowerCase()} to see and edit its
          members.
        </p>
      )}
      {creating ? (
        <NewCollection
          projectId={projectId}
          term={term}
          onClose={() => setCreating(false)}
        />
      ) : null}
    </div>
  )
}
