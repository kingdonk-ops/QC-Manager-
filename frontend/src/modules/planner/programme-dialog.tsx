import { useMemo, useState } from 'react'
import type { ColDef, ICellRendererParams } from 'ag-grid-community'
import { CalendarRange } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { Badge } from '@/components/ui/badge'
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
import { Switch } from '@/components/ui/switch'
import { DataGrid } from '@/components/data-grid'
import { NativeSelect } from '@/components/native-select'
import {
  type Plan,
  type ProgrammeActivity,
  plannerApi,
  usePlannerMutation,
  useProgramme,
} from './api'
import { anchorsLabel } from './board-lib'

/** Pick P6 activities from the mirrored programme and turn them into work packs. */
export function ProgrammeDialog({
  plan,
  open,
  onOpenChange,
}: {
  plan: Plan
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const { t } = useTranslation()
  const [search, setSearch] = useState('')
  const [whole, setWhole] = useState(false)
  const [grouping, setGrouping] = useState<'rsw' | 'activity'>('rsw')
  const [picked, setPicked] = useState<number[]>([])
  const { data: rows = [], isFetching } = useProgramme(
    plan.id,
    search,
    whole,
    open
  )
  const add = usePlannerMutation(plannerApi.fromProgramme)
  const columns = useMemo<ColDef<ProgrammeActivity>[]>(
    () => [
      {
        field: 'p6_activity_id',
        headerName: t('planner.p6_id'),
        width: 120,
      },
      { field: 'name', headerName: t('planner.activity'), flex: 1 },
      { field: 'planned_start', headerName: t('planner.start'), width: 110 },
      { field: 'planned_finish', headerName: t('planner.end'), width: 110 },
      {
        field: 'budget_hours',
        headerName: t('planner.hours'),
        width: 90,
        type: 'rightAligned',
      },
      {
        field: 'hours_in_window',
        headerName: t('planner.hours_in_plan'),
        headerTooltip: t('planner.hours_in_plan_hint'),
        width: 120,
        type: 'rightAligned',
      },
      {
        colId: 'anchors',
        headerName: t('planner.rsws'),
        width: 180,
        valueGetter: (p) => (p.data ? anchorsLabel(p.data) : ''),
        cellRenderer: (p: ICellRendererParams<ProgrammeActivity>) =>
          p.data && !p.data.anchors.length ? (
            <span className='text-muted-foreground'>
              {t('planner.not_linked')}
            </span>
          ) : (
            p.value
          ),
      },
      {
        field: 'in_plan',
        headerName: '',
        width: 90,
        cellRenderer: (p: ICellRendererParams<ProgrammeActivity>) =>
          p.value ? (
            <Badge variant='outline'>{t('planner.in_plan')}</Badge>
          ) : null,
      },
    ],
    [t]
  )
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className='sm:max-w-5xl'>
        <DialogHeader>
          <DialogTitle>{t('planner.from_programme')}</DialogTitle>
        </DialogHeader>
        <p className='text-sm text-muted-foreground'>
          {t('planner.from_programme_hint')}
        </p>
        <div className='flex flex-wrap items-end gap-3'>
          <Input
            className='h-8 w-64'
            placeholder={t('planner.programme_search')}
            aria-label={t('planner.programme_search')}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <div className='flex items-center gap-2'>
            <Switch
              id='programme-whole'
              checked={whole}
              onCheckedChange={setWhole}
            />
            <Label htmlFor='programme-whole'>
              {t('planner.whole_programme')}
            </Label>
          </div>
          <div className='grid gap-1'>
            <Label htmlFor='programme-grouping'>{t('planner.grouping')}</Label>
            <NativeSelect
              id='programme-grouping'
              className='h-8 w-56'
              options={[
                { value: 'rsw', label: t('planner.grouping.rsw') },
                { value: 'activity', label: t('planner.grouping.activity') },
              ]}
              value={grouping}
              onChange={(e) =>
                setGrouping(e.target.value === 'activity' ? 'activity' : 'rsw')
              }
            />
          </div>
        </div>
        <div className='h-[420px]'>
          <DataGrid<ProgrammeActivity>
            rowData={rows}
            columnDefs={columns}
            loading={isFetching}
            getRowId={(p) => String(p.data.activity_id)}
            rowSelection={{
              mode: 'multiRow',
              isRowSelectable: (n) => !!n.data?.anchors.length,
            }}
            onSelectionChanged={(e) =>
              setPicked(e.api.getSelectedRows().map((r) => r.activity_id))
            }
          />
        </div>
        <DialogFooter>
          <span className='me-auto text-sm text-muted-foreground'>
            {t('planner.picked', { count: picked.length })}
          </span>
          <Button
            disabled={!picked.length || add.isPending}
            onClick={() =>
              add.mutate(
                {
                  planId: plan.id,
                  body: { activity_ids: picked.slice(0, 500), grouping },
                },
                {
                  onSuccess: (r) => {
                    toast.success(
                      t('planner.from_programme_done', {
                        packs: r.packs_created,
                        lines: r.lines_added,
                        skipped: r.already_in_plan,
                      })
                    )
                    if (r.unlinked.length)
                      toast.warning(
                        t('planner.from_programme_unlinked', {
                          ids: r.unlinked.join(', '),
                        })
                      )
                    setPicked([])
                    onOpenChange(false)
                  },
                }
              )
            }
          >
            <CalendarRange /> {t('planner.add_packs')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
