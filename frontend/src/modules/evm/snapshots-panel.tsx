import { useMemo, useState } from 'react'
import type { CellClassParams, ColDef } from 'ag-grid-community'
import { Camera, Flag, GitCompare, Trash2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { can, useSession } from '@/lib/session'
import { cn } from '@/lib/utils'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { DataGrid } from '@/components/data-grid'
import {
  type SnapshotCompare,
  useCompare,
  useCreateSnapshot,
  useDeleteSnapshot,
  useSetBaseline,
  useSnapshots,
} from './api'

type CompareRow = SnapshotCompare['rows'][number]

const delta = (p: CellClassParams<CompareRow>) =>
  cn(
    'tabular-nums',
    Number(p.value) > 0 && 'text-red-600',
    Number(p.value) < 0 && 'text-green-600'
  )

/** Freeze the budget, pick the active baseline, and compare the current budget with any snapshot. */
export function SnapshotsPanel({
  projectId,
  dataDate,
}: {
  projectId: number
  dataDate: string
}) {
  const { t } = useTranslation()
  const session = useSession()
  const { data: snapshots = [] } = useSnapshots(projectId)
  const create = useCreateSnapshot(projectId)
  const setBaseline = useSetBaseline(projectId)
  const remove = useDeleteSnapshot(projectId)
  const [name, setName] = useState('')
  const [asBaseline, setAsBaseline] = useState(true)
  const [comparing, setComparing] = useState<number | null>(null)
  const { data: compare } = useCompare(projectId, comparing, dataDate)

  const columns = useMemo<ColDef<CompareRow>[]>(
    () => [
      { field: 'code', headerName: t('evm.code'), width: 110, pinned: 'left' },
      { field: 'name', headerName: t('evm.name'), flex: 1, minWidth: 180 },
      {
        field: 'status',
        headerName: t('evm.status'),
        width: 110,
        valueFormatter: (p) => t(`evm.compare_${p.value}`),
      },
      {
        field: 'snapshot_hours',
        headerName: t('evm.snapshot_hours'),
        type: 'rightAligned',
        width: 120,
      },
      {
        field: 'current_hours',
        headerName: t('evm.current_hours'),
        type: 'rightAligned',
        width: 120,
      },
      {
        field: 'delta_hours',
        headerName: t('evm.delta'),
        type: 'rightAligned',
        width: 100,
        cellClass: delta,
      },
      {
        field: 'snapshot_finish',
        headerName: t('evm.snapshot_finish'),
        width: 120,
      },
      {
        field: 'current_finish',
        headerName: t('evm.current_finish'),
        width: 120,
      },
      {
        field: 'snapshot_pv',
        headerName: t('evm.snapshot_pv'),
        type: 'rightAligned',
        width: 120,
      },
      {
        field: 'current_pv',
        headerName: t('evm.current_pv'),
        type: 'rightAligned',
        width: 120,
      },
    ],
    [t]
  )

  return (
    <div className='flex flex-col gap-4'>
      {can(session, 'evm.create') ? (
        <form
          className='flex flex-wrap items-center gap-3'
          onSubmit={(e) => {
            e.preventDefault()
            create.mutate(
              { name, set_as_baseline: asBaseline },
              { onSuccess: () => setName('') }
            )
          }}
        >
          <Input
            className='h-8 w-64'
            placeholder={t('evm.snapshot_name')}
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
          />
          <Label className='flex items-center gap-2 text-sm font-normal'>
            <Checkbox
              checked={asBaseline}
              onCheckedChange={(v) => setAsBaseline(v === true)}
            />
            {t('evm.make_baseline')}
          </Label>
          <Button size='sm' type='submit' disabled={create.isPending}>
            <Camera /> {t('evm.freeze_budget')}
          </Button>
        </form>
      ) : null}

      <ul className='divide-y rounded-md border'>
        {snapshots.length === 0 ? (
          <li className='p-3 text-sm text-muted-foreground'>
            {t('evm.no_snapshots')}
          </li>
        ) : null}
        {snapshots.map((s) => (
          <li key={s.id} className='flex flex-wrap items-center gap-3 p-3'>
            <div className='min-w-0 flex-1'>
              <p className='font-medium'>
                {s.name}{' '}
                {s.is_baseline ? (
                  <Badge variant='secondary' className='ms-1'>
                    {t('evm.baseline')}
                  </Badge>
                ) : null}
              </p>
              <p className='text-xs text-muted-foreground tabular-nums'>
                {new Date(s.created_at).toLocaleString()} · {s.package_count}{' '}
                {t('evm.packages')} · {s.budget_hours.toLocaleString()} h
              </p>
            </div>
            <Button
              size='sm'
              variant={comparing === s.id ? 'default' : 'outline'}
              onClick={() => setComparing(comparing === s.id ? null : s.id)}
            >
              <GitCompare /> {t('evm.compare')}
            </Button>
            {can(session, 'evm.update') && !s.is_baseline ? (
              <Button
                size='sm'
                variant='outline'
                onClick={() => setBaseline.mutate({ id: s.id, value: true })}
              >
                <Flag /> {t('evm.make_baseline')}
              </Button>
            ) : null}
            {can(session, 'evm.delete') ? (
              <Button
                size='icon'
                variant='ghost'
                aria-label={t('evm.delete')}
                onClick={() => {
                  if (comparing === s.id) setComparing(null)
                  remove.mutate(s.id)
                }}
              >
                <Trash2 className='size-4' />
              </Button>
            ) : null}
          </li>
        ))}
      </ul>

      {compare ? (
        <div className='flex flex-col gap-2'>
          <p className='text-sm text-muted-foreground tabular-nums'>
            {t('evm.compare_summary', {
              name: compare.snapshot.name,
              before: compare.snapshot_hours.toLocaleString(),
              now: compare.current_hours.toLocaleString(),
              pvBefore: compare.snapshot_pv.toLocaleString(),
              pvNow: compare.current_pv.toLocaleString(),
              date: compare.data_date,
            })}
          </p>
          <div className='h-[360px]'>
            <DataGrid<CompareRow>
              rowData={compare.rows}
              columnDefs={columns}
              getRowId={(p) => p.data.code}
            />
          </div>
        </div>
      ) : null}
    </div>
  )
}
