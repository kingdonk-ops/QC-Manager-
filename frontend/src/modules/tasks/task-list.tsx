import { useMemo } from 'react'
import type { ColDef, ICellRendererParams } from 'ag-grid-community'
import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'
import { DataGrid } from '@/components/data-grid'
import { StatusBadge } from '@/components/records/status-badge'
import { type Task, type TaskUpdate, useUpdateTask } from './api'
import { PRIORITIES, STATUSES, TYPE_COLOURS, formatDate } from './constants'

export function TaskList({
  tasks,
  projectId,
  editable,
  onOpen,
}: {
  tasks: Task[]
  projectId: number
  editable: boolean
  onOpen: (task: Task) => void
}) {
  const { t } = useTranslation()
  const update = useUpdateTask(projectId)

  const columns = useMemo<ColDef<Task>[]>(
    () => [
      {
        field: 'code',
        headerName: t('tasks.code'),
        width: 110,
        pinned: 'left',
        cellClass: 'font-mono',
      },
      {
        field: 'title',
        headerName: t('tasks.title_field'),
        flex: 1,
        minWidth: 240,
        cellClass: 'cursor-pointer',
        onCellClicked: (p) => p.data && onOpen(p.data),
      },
      {
        field: 'type',
        headerName: t('tasks.type'),
        width: 150,
        cellRenderer: (p: ICellRendererParams<Task>) => (
          <span className='flex items-center gap-2 capitalize'>
            <span
              className={cn('size-2 rounded-full', TYPE_COLOURS[p.value])}
            />
            {p.value}
          </span>
        ),
      },
      {
        field: 'status',
        headerName: t('tasks.status_field'),
        width: 140,
        editable,
        cellEditor: 'agSelectCellEditor',
        cellEditorParams: { values: STATUSES },
        cellRenderer: (p: ICellRendererParams<Task>) => (
          <StatusBadge status={p.value} />
        ),
      },
      {
        field: 'priority',
        headerName: t('tasks.priority'),
        width: 120,
        editable,
        cellEditor: 'agSelectCellEditor',
        cellEditorParams: { values: PRIORITIES },
        cellRenderer: (p: ICellRendererParams<Task>) => (
          <StatusBadge status={p.value} />
        ),
      },
      {
        field: 'assignee_name',
        headerName: t('tasks.assignee'),
        width: 170,
      },
      {
        field: 'due_date',
        headerName: t('tasks.due'),
        width: 130,
        editable,
        cellEditor: 'agDateStringCellEditor',
        valueFormatter: (p) => formatDate(p.value),
        cellClass: (p) =>
          p.data?.overdue
            ? 'font-medium text-red-600 dark:text-red-400'
            : undefined,
      },
    ],
    [editable, onOpen, t]
  )

  return (
    <div className='h-[560px]'>
      <DataGrid<Task>
        rowData={tasks}
        columnDefs={columns}
        getRowId={(p) => String(p.data.id)}
        getRowClass={(p) => (p.data?.overdue ? 'bg-red-500/5' : undefined)}
        singleClickEdit
        onCellValueChanged={(e) => {
          const field = e.colDef.field as keyof TaskUpdate | undefined
          if (!e.data || !field || e.newValue === e.oldValue) return
          update.mutate({
            id: e.data.id,
            body: { [field]: e.newValue || null } as TaskUpdate,
          })
        }}
      />
    </div>
  )
}
