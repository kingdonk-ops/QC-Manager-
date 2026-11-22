import { useState } from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Checkbox } from '@/components/ui/checkbox'
import { type TreeNode, useCollections, useTreeChildren } from './api'

function Branch({
  projectId,
  parentId,
  selected,
  toggle,
  depth,
}: {
  projectId: number
  parentId: number | null
  selected: number[]
  toggle: (id: number) => void
  depth: number
}) {
  const { data: nodes = [], isLoading } = useTreeChildren(projectId, parentId)
  const { t } = useTranslation()
  if (isLoading) return null
  if (!nodes.length && depth === 0)
    return (
      <p className='text-xs text-muted-foreground'>{t('mdr.scope_no_tree')}</p>
    )
  return (
    <ul className='grid gap-0.5'>
      {nodes.map((n) => (
        <NodeRow
          key={n.id}
          node={n}
          projectId={projectId}
          selected={selected}
          toggle={toggle}
          depth={depth}
        />
      ))}
    </ul>
  )
}

function NodeRow({
  node,
  projectId,
  selected,
  toggle,
  depth,
}: {
  node: TreeNode
  projectId: number
  selected: number[]
  toggle: (id: number) => void
  depth: number
}) {
  const [open, setOpen] = useState(false)
  const hasChildren = node.child_count > 0
  return (
    <li>
      <div
        className='flex items-center gap-1 text-sm'
        style={{ paddingInlineStart: depth * 16 }}
      >
        <button
          type='button'
          className='size-5 text-muted-foreground disabled:opacity-0'
          disabled={!hasChildren}
          aria-label={open ? 'Collapse' : 'Expand'}
          onClick={() => setOpen(!open)}
        >
          {open ? (
            <ChevronDown className='size-4' />
          ) : (
            <ChevronRight className='size-4' />
          )}
        </button>
        <label className='flex items-center gap-2'>
          <Checkbox
            checked={selected.includes(node.id)}
            onCheckedChange={() => toggle(node.id)}
          />
          <span className='font-mono text-xs'>{node.code}</span>
          {node.name ? (
            <span className='text-muted-foreground'>{node.name}</span>
          ) : null}
          <span className='text-xs text-muted-foreground'>
            {node.level_key}
          </span>
        </label>
      </div>
      {open && hasChildren ? (
        <Branch
          projectId={projectId}
          parentId={node.id}
          selected={selected}
          toggle={toggle}
          depth={depth + 1}
        />
      ) : null}
    </li>
  )
}

/** Pick asset nodes (their subtrees are included) and collections. Nothing picked: the whole project. */
export function ScopePicker({
  projectId,
  nodeIds,
  collectionIds,
  onChange,
}: {
  projectId: number
  nodeIds: number[]
  collectionIds: number[]
  onChange: (nodeIds: number[], collectionIds: number[]) => void
}) {
  const { t } = useTranslation()
  const { data: collections = [] } = useCollections(projectId)
  const flip = (list: number[], id: number) =>
    list.includes(id) ? list.filter((x) => x !== id) : [...list, id]
  return (
    <div className='grid gap-3'>
      <div className='max-h-64 overflow-y-auto rounded-md border p-2'>
        <Branch
          projectId={projectId}
          parentId={null}
          selected={nodeIds}
          toggle={(id) => onChange(flip(nodeIds, id), collectionIds)}
          depth={0}
        />
      </div>
      {collections.length ? (
        <div className='grid gap-1'>
          <span className='text-xs font-medium'>{t('mdr.collections')}</span>
          <div className='flex flex-wrap gap-3'>
            {collections.map((c) => (
              <label key={c.id} className='flex items-center gap-2 text-sm'>
                <Checkbox
                  checked={collectionIds.includes(c.id)}
                  onCheckedChange={() =>
                    onChange(nodeIds, flip(collectionIds, c.id))
                  }
                />
                <span className='font-mono text-xs'>{c.code}</span>
                {c.name}
                <span className='text-xs text-muted-foreground'>{c.kind}</span>
              </label>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  )
}
