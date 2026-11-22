import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Input } from '@/components/ui/input'
import { useNodeSearch } from './api'

/** Find an asset-tree node by code, name or path. */
export function NodePicker({
  projectId,
  value,
  onChange,
}: {
  projectId: number
  value?: { id: number; label: string }
  onChange: (node: { id: number; label: string }) => void
}) {
  const { t } = useTranslation()
  const [search, setSearch] = useState('')
  const { data: nodes = [] } = useNodeSearch(projectId, search)
  return (
    <div className='grid gap-1'>
      <Input
        placeholder={value?.label ?? t('welding.find_node')}
        value={search}
        onChange={(e) => setSearch(e.target.value)}
      />
      {search && nodes.length ? (
        <ul className='max-h-40 overflow-y-auto rounded-md border text-sm'>
          {nodes.map((n) => (
            <li key={n.id}>
              <button
                type='button'
                className='w-full px-2 py-1 text-left hover:bg-muted'
                onClick={() => {
                  onChange({ id: n.id, label: n.display_path })
                  setSearch('')
                }}
              >
                {n.display_path}
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  )
}
