/**
 * The lazy breakdown tree: a node's children load when it is expanded. Nodes can be dragged onto
 * another node (or the top) to move them with their subtree; the server checks the level rules.
 */
import { useState, type DragEvent } from 'react'
import { ChevronDown, ChevronRight, Loader2 } from 'lucide-react'
import { cn } from '@/lib/utils'
import { type TreeNode, useChildren } from './api'
import type { TermFn } from './terminology'

const DRAG_TYPE = 'application/x-asset-node'

type TreeProps = {
  projectId: number
  selectedId: number | null
  expanded: Set<number>
  onToggle: (id: number) => void
  onSelect: (node: TreeNode) => void
  onMove?: (nodeId: number, parentId: number | null) => void
  showRetired: boolean
  term: TermFn
}

function draggedId(e: DragEvent) {
  const raw = e.dataTransfer.getData(DRAG_TYPE)
  return raw ? Number(raw) : null
}

function Row({
  node,
  depth,
  ...props
}: TreeProps & { node: TreeNode; depth: number }) {
  const { expanded, onToggle, onSelect, selectedId, onMove, term } = props
  const open = expanded.has(node.id)
  const [over, setOver] = useState(false)
  const retired = node.status === 'retired'
  return (
    <li>
      <div
        role='treeitem'
        aria-selected={selectedId === node.id}
        aria-expanded={node.child_count ? open : undefined}
        tabIndex={0}
        draggable={Boolean(onMove) && !retired}
        onDragStart={(e) => {
          e.dataTransfer.setData(DRAG_TYPE, String(node.id))
          e.dataTransfer.effectAllowed = 'move'
        }}
        onDragOver={(e) => {
          if (!onMove || retired) return
          e.preventDefault()
          setOver(true)
        }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => {
          setOver(false)
          const id = draggedId(e)
          if (onMove && id && id !== node.id) {
            e.preventDefault()
            onMove(id, node.id)
          }
        }}
        onClick={() => onSelect(node)}
        onKeyDown={(e) => {
          if (e.key === 'Enter') onSelect(node)
          if (e.key === 'ArrowRight' && !open && node.child_count)
            onToggle(node.id)
          if (e.key === 'ArrowLeft' && open) onToggle(node.id)
        }}
        className={cn(
          'flex cursor-pointer items-center gap-1 rounded-md py-1 pe-2 text-sm hover:bg-muted',
          selectedId === node.id && 'bg-primary/10 font-medium',
          over && 'ring-2 ring-primary',
          retired && 'text-muted-foreground line-through'
        )}
        style={{ paddingInlineStart: depth * 14 + 4 }}
      >
        <button
          type='button'
          aria-label={open ? 'Collapse' : 'Expand'}
          className={cn(
            'grid size-5 shrink-0 place-items-center rounded hover:bg-accent',
            !node.child_count && 'invisible'
          )}
          onClick={(e) => {
            e.stopPropagation()
            onToggle(node.id)
          }}
        >
          {open ? (
            <ChevronDown className='size-3.5' />
          ) : (
            <ChevronRight className='size-3.5' />
          )}
        </button>
        <span className='shrink-0 rounded bg-muted px-1 text-[10px] tracking-wide text-muted-foreground uppercase'>
          {term(`level.${node.level_key}`)}
        </span>
        <span className='truncate font-mono'>{node.code}</span>
        {node.name ? (
          <span className='truncate text-muted-foreground'>{node.name}</span>
        ) : null}
        {node.item_count ? (
          <span className='ms-auto shrink-0 text-xs text-muted-foreground'>
            {node.item_count}
          </span>
        ) : null}
      </div>
      {open ? <Level parentId={node.id} depth={depth + 1} {...props} /> : null}
    </li>
  )
}

function Level({
  parentId,
  depth,
  ...props
}: TreeProps & { parentId: number | null; depth: number }) {
  const { data, isLoading } = useChildren(
    props.projectId,
    parentId,
    true,
    props.showRetired
  )
  if (isLoading)
    return (
      <div
        className='flex items-center gap-1 py-1 text-xs text-muted-foreground'
        style={{ paddingInlineStart: depth * 14 + 8 }}
      >
        <Loader2 className='size-3 animate-spin' /> Loading…
      </div>
    )
  return (
    <ul role={depth ? 'group' : undefined}>
      {(data ?? []).map((node) => (
        <Row key={node.id} node={node} depth={depth} {...props} />
      ))}
    </ul>
  )
}

export function TreeView(props: TreeProps) {
  const [overRoot, setOverRoot] = useState(false)
  const { data: roots } = useChildren(
    props.projectId,
    null,
    true,
    props.showRetired
  )
  return (
    <div role='tree' aria-label='Breakdown' className='grid gap-1'>
      {props.onMove ? (
        <div
          onDragOver={(e) => {
            e.preventDefault()
            setOverRoot(true)
          }}
          onDragLeave={() => setOverRoot(false)}
          onDrop={(e) => {
            setOverRoot(false)
            const id = draggedId(e)
            if (id) props.onMove?.(id, null)
          }}
          className={cn(
            'rounded-md border border-dashed px-2 py-0.5 text-center text-[11px] text-muted-foreground',
            overRoot ? 'border-primary text-primary' : 'opacity-60'
          )}
        >
          Drop here to move to the top
        </div>
      ) : null}
      <Level parentId={null} depth={0} {...props} />
      {roots?.length === 0 ? (
        <p className='p-2 text-sm text-muted-foreground'>
          Nothing here yet. Add a top-level{' '}
          {props.term('noun.node').toLowerCase()} or import a spreadsheet.
        </p>
      ) : null}
    </div>
  )
}
