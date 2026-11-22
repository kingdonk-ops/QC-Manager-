/**
 * Pick nodes from the project's asset hierarchy (Site / Area / Asset / RSW...): browse level by
 * level, or search every level. `NodeBrowser` lists and picks; `NodeSelect` is a one-node field.
 * Records that book work resolve the picked node to its work anchor on the server.
 */
import { useState } from 'react'
import { ChevronRight, Search, X } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover'
import { type AssetNode, nodeLabel, useNodes } from './asset-nodes'

export function NodeBrowser({
  projectId,
  onPick,
  picked = [],
  className,
}: {
  projectId: number
  onPick: (node: AssetNode) => void
  picked?: number[]
  className?: string
}) {
  const [trail, setTrail] = useState<AssetNode[]>([])
  const [search, setSearch] = useState('')
  const parent = trail.length ? trail[trail.length - 1] : null
  const { data: nodes = [], isLoading } = useNodes(
    projectId,
    parent?.id ?? null,
    search.trim()
  )
  return (
    <div className={cn('grid gap-2', className)}>
      <div className='relative'>
        <Search className='absolute top-2.5 left-2 size-4 text-muted-foreground' />
        <Input
          className='h-9 ps-8'
          placeholder='Search the asset tree'
          aria-label='Search the asset tree'
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>
      {!search ? (
        <div className='flex flex-wrap items-center gap-1 text-xs'>
          <button
            type='button'
            className='text-primary hover:underline'
            onClick={() => setTrail([])}
          >
            Top
          </button>
          {trail.map((n, i) => (
            <span key={n.id} className='flex items-center gap-1'>
              <ChevronRight className='size-3' />
              <button
                type='button'
                className='text-primary hover:underline'
                onClick={() => setTrail(trail.slice(0, i + 1))}
              >
                {n.code}
              </button>
            </span>
          ))}
        </div>
      ) : null}
      <ul className='max-h-72 divide-y overflow-y-auto rounded-md border text-sm'>
        {isLoading ? (
          <li className='p-2 text-muted-foreground'>Loading…</li>
        ) : nodes.length === 0 ? (
          <li className='p-2 text-muted-foreground'>Nothing here.</li>
        ) : (
          nodes.map((n) => (
            <li key={n.id} className='flex items-center gap-2 px-2 py-1.5'>
              <div className='min-w-0 flex-1'>
                <div className='truncate font-medium'>
                  {nodeLabel(n)}
                  <span className='ms-2 text-xs font-normal text-muted-foreground'>
                    {n.level_key}
                  </span>
                </div>
                <div className='truncate text-xs text-muted-foreground'>
                  {n.name || n.display_path}
                </div>
              </div>
              <Button
                type='button'
                size='sm'
                variant={picked.includes(n.id) ? 'secondary' : 'outline'}
                className='h-7'
                onClick={() => onPick(n)}
              >
                {picked.includes(n.id) ? 'Added' : 'Pick'}
              </Button>
              {!search && (n.child_count ?? 0) > 0 ? (
                <Button
                  type='button'
                  size='icon'
                  variant='ghost'
                  className='size-7'
                  aria-label={`Open ${n.code}`}
                  onClick={() => setTrail([...trail, n])}
                >
                  <ChevronRight />
                </Button>
              ) : null}
            </li>
          ))
        )}
      </ul>
    </div>
  )
}

/** One node as a form field: shows the picked node's label, opens the browser to change it. */
export function NodeSelect({
  projectId,
  value,
  label,
  onChange,
  placeholder = 'Pick a location',
  className,
}: {
  projectId: number
  value: number | null | undefined
  label?: string | null
  onChange: (id: number | null, node?: AssetNode) => void
  placeholder?: string
  className?: string
}) {
  const [open, setOpen] = useState(false)
  return (
    <div className={cn('flex min-w-0 items-center gap-1', className)}>
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <Button
            type='button'
            variant='outline'
            className='h-9 min-w-0 flex-1 justify-start truncate font-normal'
          >
            {value ? (
              (label ?? `#${value}`)
            ) : (
              <span className='text-muted-foreground'>{placeholder}</span>
            )}
          </Button>
        </PopoverTrigger>
        <PopoverContent className='w-80' align='start'>
          <NodeBrowser
            projectId={projectId}
            picked={value ? [value] : []}
            onPick={(n) => {
              onChange(n.id, n)
              setOpen(false)
            }}
          />
        </PopoverContent>
      </Popover>
      {value ? (
        <Button
          type='button'
          size='icon'
          variant='ghost'
          className='size-8'
          aria-label='Clear'
          onClick={() => onChange(null)}
        >
          <X />
        </Button>
      ) : null}
    </div>
  )
}
