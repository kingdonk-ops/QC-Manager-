import { useMemo, useState } from 'react'
import type { ColDef, ValueParserParams } from 'ag-grid-community'
import { Save, Undo2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { can, useSession } from '@/lib/session'
import { Button } from '@/components/ui/button'
import { DataGrid } from '@/components/data-grid'
import {
  type ProgressEntry,
  type ProgressRow,
  useProgress,
  useSaveProgress,
} from './api'

type Editable = 'percent_complete' | 'actual_hours' | 'actual_cost' | 'comment'
type Draft = Partial<Record<Editable, string | null>>

const number =
  (max?: number) =>
  (p: ValueParserParams<ProgressRow>): string => {
    const n = Number(String(p.newValue ?? '').replace(/[^0-9.]/g, ''))
    if (p.newValue === '' || p.newValue === null || !Number.isFinite(n))
      return p.oldValue
    return String(max === undefined ? n : Math.min(n, max))
  }

/** Cumulative % complete and actual hours per package for the data date; edits are saved together. */
export function ProgressGrid({
  projectId,
  dataDate,
  costAvailable,
}: {
  projectId: number
  dataDate: string
  costAvailable: boolean
}) {
  const { t } = useTranslation()
  const editable = can(useSession(), 'evm.update')
  const { data } = useProgress(projectId, dataDate)
  const save = useSaveProgress(projectId)
  const [drafts, setDrafts] = useState<Record<number, Draft>>({})
  const [loadedFor, setLoadedFor] = useState(dataDate)
  if (loadedFor !== dataDate) {
    setLoadedFor(dataDate)
    setDrafts({})
  }

  const rows = useMemo(
    () =>
      (data?.rows ?? []).map(
        (r) => ({ ...r, ...drafts[r.work_package_id] }) as ProgressRow
      ),
    [data, drafts]
  )

  const columns = useMemo<ColDef<ProgressRow>[]>(() => {
    const edit = (row: ProgressRow | undefined) => editable && !!row
    return [
      {
        field: 'code',
        headerName: t('evm.code'),
        width: 110,
        pinned: 'left',
        cellClass: 'font-mono',
      },
      { field: 'name', headerName: t('evm.name'), flex: 1, minWidth: 200 },
      {
        field: 'control_account',
        headerName: t('evm.control_account'),
        width: 130,
      },
      {
        field: 'budget_hours',
        headerName: t('evm.budget_hours'),
        type: 'rightAligned',
        width: 110,
        cellClass: 'tabular-nums',
      },
      {
        field: 'percent_complete',
        headerName: t('evm.percent_complete'),
        type: 'rightAligned',
        width: 110,
        editable: (p) => edit(p.data),
        valueParser: number(100),
        cellClass: 'tabular-nums bg-blue-50/40 dark:bg-blue-950/20',
      },
      {
        headerName: t('evm.earned_hours'),
        type: 'rightAligned',
        width: 110,
        valueGetter: (p) =>
          p.data
            ? (
                (Number(p.data.budget_hours) *
                  Number(p.data.percent_complete)) /
                100
              ).toFixed(2)
            : null,
        cellClass: 'tabular-nums text-muted-foreground',
      },
      {
        field: 'actual_hours',
        headerName: t('evm.actual_hours'),
        type: 'rightAligned',
        width: 120,
        editable: (p) => edit(p.data),
        valueParser: number(),
        cellClass: 'tabular-nums bg-blue-50/40 dark:bg-blue-950/20',
      },
      ...(costAvailable
        ? [
            {
              field: 'actual_cost',
              headerName: t('evm.actual_cost'),
              type: 'rightAligned',
              width: 120,
              editable: (p) => edit(p.data),
              valueParser: number(),
              cellClass: 'tabular-nums',
            } satisfies ColDef<ProgressRow>,
          ]
        : []),
      {
        field: 'recorded_on',
        headerName: t('evm.recorded_on'),
        width: 120,
        valueFormatter: (p) => p.value ?? '—',
      },
      {
        field: 'comment',
        headerName: t('evm.comment'),
        width: 220,
        editable: (p) => edit(p.data),
      },
    ]
  }, [costAvailable, editable, t])

  const changed = Object.keys(drafts).length

  const submit = () => {
    const entries: ProgressEntry[] = Object.entries(drafts).map(([id, d]) => ({
      work_package_id: Number(id),
      ...(d.percent_complete != null
        ? { percent_complete: d.percent_complete }
        : {}),
      ...(d.actual_hours != null ? { actual_hours: d.actual_hours } : {}),
      ...(d.actual_cost != null ? { actual_cost: d.actual_cost } : {}),
      ...(d.comment !== undefined ? { comment: d.comment ?? '' } : {}),
    }))
    save.mutate(
      { data_date: dataDate, entries },
      {
        onSuccess: (res) => {
          setDrafts({})
          toast.success(t('evm.saved', { count: res.saved }))
        },
      }
    )
  }

  return (
    <div className='flex flex-col gap-2'>
      <div className='flex flex-wrap items-center gap-2'>
        <p className='text-sm text-muted-foreground'>
          {t('evm.progress_help', { date: dataDate })}
        </p>
        {editable ? (
          <div className='ms-auto flex gap-2'>
            <Button
              size='sm'
              variant='outline'
              disabled={!changed}
              onClick={() => setDrafts({})}
            >
              <Undo2 /> {t('evm.discard')}
            </Button>
            <Button
              size='sm'
              disabled={!changed || save.isPending}
              onClick={submit}
            >
              <Save /> {t('evm.save_all', { count: changed })}
            </Button>
          </div>
        ) : null}
      </div>
      <div className='h-[460px]'>
        <DataGrid<ProgressRow>
          rowData={rows}
          columnDefs={columns}
          getRowId={(p) => String(p.data.work_package_id)}
          getRowClass={(p) =>
            p.data && drafts[p.data.work_package_id]
              ? 'bg-amber-50 dark:bg-amber-950/30'
              : undefined
          }
          singleClickEdit
          onCellValueChanged={(e) => {
            const field = e.colDef.field as Editable | undefined
            if (!e.data || !field || e.newValue === e.oldValue) return
            const id = e.data.work_package_id
            setDrafts((all) => ({
              ...all,
              [id]: {
                ...all[id],
                [field]: e.newValue === null ? null : String(e.newValue),
              },
            }))
          }}
        />
      </div>
    </div>
  )
}
