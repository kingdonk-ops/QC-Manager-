/**
 * Pick a node of the project's asset breakdown (site / area / asset / RSW) by typing part of its code or name.
 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api, unwrap } from '@/api/client'
import { Input } from '@/components/ui/input'
import { NativeSelect } from '@/components/native-select'

export function NodeSelect({
  projectId,
  value,
  onChange,
  id,
  placeholder = 'Type to find an area, asset or RSW',
}: {
  projectId: number
  value: number | null
  onChange: (id: number | null) => void
  id?: string
  placeholder?: string
}) {
  const [search, setSearch] = useState('')
  const { data = [] } = useQuery({
    queryKey: ['asset-tree', projectId, 'node-search', search],
    enabled: search.trim().length > 0,
    queryFn: async () =>
      (
        await unwrap(
          api.GET('/api/v1/asset-tree/nodes/', {
            params: {
              query: {
                project_id: projectId,
                search: search.trim(),
                items_per_page: 50,
              },
            },
          })
        )
      ).data,
  })
  const options = data.map((n) => ({
    value: String(n.id),
    label: n.display_path || n.code,
  }))
  if (value && !options.some((o) => o.value === String(value)))
    options.unshift({ value: String(value), label: `Node ${value}` })
  return (
    <div className='grid gap-1.5'>
      <Input
        id={id}
        placeholder={placeholder}
        value={search}
        onChange={(e) => setSearch(e.target.value)}
      />
      <NativeSelect
        aria-label='Node'
        options={options}
        placeholder='—'
        value={value ? String(value) : ''}
        onChange={(e) =>
          onChange(e.target.value ? Number(e.target.value) : null)
        }
      />
    </div>
  )
}
