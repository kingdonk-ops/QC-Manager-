import { useState } from 'react'
import { Link2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { NodePicker, type PickedNode } from '@/components/records/node-picker'
import { type Unmatched, useLinkActions, useUnmatched } from './api'

function Row({ projectId, row }: { projectId: number; row: Unmatched }) {
  const { t } = useTranslation()
  const { link, confirm } = useLinkActions(projectId)
  const [node, setNode] = useState<PickedNode | null>(null)
  const [remember, setRemember] = useState(true)
  return (
    <li className='grid gap-2 rounded-lg border p-3 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto] md:items-center'>
      <div className='min-w-0'>
        <p className='truncate text-sm font-medium'>
          <span className='font-mono text-muted-foreground'>
            {row.p6_activity_id}
          </span>{' '}
          {row.name}
        </p>
        <p className='text-xs text-muted-foreground'>
          {[row.wbs_path, row.planned_start, row.reason]
            .filter(Boolean)
            .join(' · ')}
        </p>
        {row.proposed.map((p) => (
          <p key={p.id} className='mt-1 flex items-center gap-2 text-xs'>
            {t('p6.proposed')}: {p.node_path}
            <Button
              size='sm'
              variant='outline'
              className='h-6'
              onClick={() => confirm.mutate(p.id)}
            >
              {t('p6.confirm')}
            </Button>
          </p>
        ))}
      </div>
      <NodePicker projectId={projectId} value={node} onChange={setNode} />
      <div className='flex items-center gap-3'>
        <label className='flex items-center gap-1.5 text-xs'>
          <Checkbox
            checked={remember}
            onCheckedChange={(v) => setRemember(v === true)}
          />
          {t('p6.remember')}
        </label>
        <Button
          size='sm'
          disabled={!node || link.isPending}
          onClick={() =>
            node &&
            link.mutate({ activityId: row.id, nodeId: node.id, remember })
          }
        >
          <Link2 className='size-4' />
          {t('p6.link')}
        </Button>
      </div>
    </li>
  )
}

/** The Unmatched-Row Linking Screen: activities the grammar couldn't place, linked by hand. */
export function UnmatchedTab({ projectId }: { projectId: number }) {
  const { t } = useTranslation()
  const { data } = useUnmatched(projectId)
  const rows = data?.data ?? []
  return (
    <div className='flex flex-col gap-3'>
      <p className='text-sm text-muted-foreground'>
        {t('p6.unmatched_hint', { count: data?.total_count ?? 0 })}
      </p>
      <ul className='flex flex-col gap-2'>
        {rows.map((row) => (
          <Row key={row.id} projectId={projectId} row={row} />
        ))}
      </ul>
    </div>
  )
}
