import { useMemo, useState } from 'react'
import type { ColDef } from 'ag-grid-community'
import { Plus, Trash2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { can, useSession } from '@/lib/session'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { DataGrid } from '@/components/data-grid'
import {
  type WorkPackage,
  useCreatePackage,
  useDeletePackage,
  useUpdatePackage,
  useWorkPackages,
} from './api'

const CURVES = ['linear', 'front_loaded', 'back_loaded', 's_curve']

const optionalText = new Set([
  'control_account',
  'wbs',
  'discipline',
  'planned_start',
  'planned_finish',
  'budget_cost',
  'schedule_activity_id',
  'cvr_cost_head_id',
])

/** Control accounts and work packages: budget hours, dates and the planned curve, edited in place. */
export function PackagesGrid({ projectId }: { projectId: number }) {
  const { t } = useTranslation()
  const session = useSession()
  const editable = can(session, 'evm.update')
  const { data: packages = [] } = useWorkPackages(projectId)
  const update = useUpdatePackage(projectId)
  const create = useCreatePackage(projectId)
  const { mutate: remove } = useDeletePackage(projectId)
  const [draft, setDraft] = useState({ code: '', name: '', budget_hours: '' })

  const columns = useMemo<ColDef<WorkPackage>[]>(() => {
    const text = (
      field: keyof WorkPackage,
      headerName: string,
      width = 130
    ): ColDef<WorkPackage> => ({ field, headerName, width, editable })
    const num = (
      field: keyof WorkPackage,
      headerName: string
    ): ColDef<WorkPackage> => ({
      field,
      headerName,
      width: 120,
      editable,
      type: 'rightAligned',
      cellClass: 'tabular-nums',
      valueParser: (p) => {
        if (p.newValue === '' || p.newValue === null) return null
        const n = Number(String(p.newValue).replace(/[^0-9.]/g, ''))
        return Number.isFinite(n) ? String(n) : p.oldValue
      },
    })
    const day = (
      field: keyof WorkPackage,
      headerName: string
    ): ColDef<WorkPackage> => ({
      field,
      headerName,
      width: 130,
      editable,
      cellEditor: 'agDateStringCellEditor',
    })
    return [
      {
        ...text('code', t('evm.code'), 110),
        pinned: 'left',
        cellClass: 'font-mono',
      },
      { ...text('name', t('evm.name')), flex: 1, minWidth: 200 },
      text('control_account', t('evm.control_account')),
      text('wbs', t('evm.wbs'), 100),
      text('discipline', t('evm.discipline')),
      day('planned_start', t('evm.planned_start')),
      day('planned_finish', t('evm.planned_finish')),
      num('budget_hours', t('evm.budget_hours')),
      num('budget_cost', t('evm.budget_cost')),
      {
        field: 'curve',
        headerName: t('evm.curve'),
        width: 130,
        editable,
        cellEditor: 'agSelectCellEditor',
        cellEditorParams: { values: CURVES },
        valueFormatter: (p) => (p.value ? t(`evm.curve_${p.value}`) : ''),
      },
      {
        ...num('schedule_activity_id', t('evm.schedule_activity')),
        valueParser: (p) =>
          p.newValue === '' || p.newValue === null
            ? null
            : Number.parseInt(String(p.newValue), 10) || p.oldValue,
      },
      ...(can(session, 'evm.delete')
        ? [
            {
              headerName: '',
              width: 48,
              sortable: false,
              filter: false,
              cellRenderer: (p: { data?: WorkPackage }) =>
                p.data ? (
                  <button
                    className='text-muted-foreground hover:text-red-600'
                    aria-label={t('evm.delete')}
                    onClick={() => remove(p.data!.id)}
                  >
                    <Trash2 className='size-4' />
                  </button>
                ) : null,
            } satisfies ColDef<WorkPackage>,
          ]
        : []),
    ]
  }, [editable, remove, session, t])

  return (
    <div className='flex flex-col gap-2'>
      {can(session, 'evm.create') ? (
        <form
          className='flex flex-wrap items-center gap-2'
          onSubmit={(e) => {
            e.preventDefault()
            create.mutate(
              {
                project_id: projectId,
                code: draft.code,
                name: draft.name,
                budget_hours: draft.budget_hours || '0',
                curve: 'linear',
                sort_order: packages.length,
              },
              {
                onSuccess: () =>
                  setDraft({ code: '', name: '', budget_hours: '' }),
              }
            )
          }}
        >
          <Input
            className='h-8 w-28 font-mono'
            placeholder={t('evm.code')}
            value={draft.code}
            onChange={(e) => setDraft({ ...draft, code: e.target.value })}
            required
          />
          <Input
            className='h-8 w-64'
            placeholder={t('evm.name')}
            value={draft.name}
            onChange={(e) => setDraft({ ...draft, name: e.target.value })}
            required
          />
          <Input
            className='h-8 w-32'
            type='number'
            min={0}
            step='0.01'
            placeholder={t('evm.budget_hours')}
            value={draft.budget_hours}
            onChange={(e) =>
              setDraft({ ...draft, budget_hours: e.target.value })
            }
          />
          <Button size='sm' type='submit' disabled={create.isPending}>
            <Plus /> {t('evm.add_package')}
          </Button>
        </form>
      ) : null}
      <div className='h-[460px]'>
        <DataGrid<WorkPackage>
          rowData={packages}
          columnDefs={columns}
          getRowId={(p) => String(p.data.id)}
          singleClickEdit
          onCellValueChanged={(e) => {
            const field = e.colDef.field
            if (!e.data || !field || e.newValue === e.oldValue) return
            const value =
              e.newValue === '' && optionalText.has(field) ? null : e.newValue
            update.mutate({ id: e.data.id, field, value })
          }}
        />
      </div>
    </div>
  )
}
