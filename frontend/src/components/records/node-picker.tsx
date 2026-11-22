import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Search, X } from 'lucide-react'
import { api, unwrap } from '@/api/client'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'

export type PickedNode = { id: number; display_path: string }

/** Search the project's asset breakdown (Site / Asset / RSW ...) and pick one node. */
export function NodePicker({
  projectId,
  value,
  onChange,
  placeholder = 'Search the breakdown…',
  disabled,
}: {
  projectId: number
  value: PickedNode | null
  onChange: (node: PickedNode | null) => void
  placeholder?: string
  disabled?: boolean
}) {
  const [search, setSearch] = useState('')
  const [open, setOpen] = useState(false)
  const { data = [] } = useQuery({
    queryKey: ['asset_tree', projectId, 'search', search],
    queryFn: async () =>
      (
        await unwrap(
          api.GET('/api/v1/asset-tree/nodes/', {
            params: {
              query: { project_id: projectId, search, items_per_page: 20 },
            },
          })
        )
      ).data,
    enabled: open && search.trim().length > 0,
  })

  if (value) {
    return (
      <div className='flex min-h-8 items-center gap-1 rounded-md border px-2 text-sm'>
        <span className='flex-1 truncate'>{value.display_path}</span>
        {disabled ? null : (
          <Button
            type='button'
            variant='ghost'
            size='icon'
            className='size-6'
            aria-label='Clear'
            onClick={() => onChange(null)}
          >
            <X className='size-3.5' />
          </Button>
        )}
      </div>
    )
  }
  return (
    <div className='relative'>
      <Search className='absolute top-2 left-2 size-4 text-muted-foreground' />
      <Input
        className='h-8 ps-8'
        value={search}
        placeholder={placeholder}
        disabled={disabled}
        onChange={(e) => {
          setSearch(e.target.value)
          setOpen(true)
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
      />
      {open && data.length > 0 ? (
        <ul className='absolute z-50 mt-1 max-h-64 w-full overflow-auto rounded-md border bg-popover p-1 text-sm shadow-md'>
          {data.map((n) => (
            <li key={n.id}>
              <button
                type='button'
                className='w-full rounded px-2 py-1.5 text-start hover:bg-accent'
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => {
                  onChange({ id: n.id, display_path: n.display_path })
                  setSearch('')
                  setOpen(false)
                }}
              >
                <span className='font-medium'>{n.code}</span>{' '}
                <span className='text-muted-foreground'>{n.display_path}</span>
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  )
}
