import { useMemo, useState } from 'react'
import type { ColDef } from 'ag-grid-community'
import { CheckCheck, Download } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { can, useSession } from '@/lib/session'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { DataGrid } from '@/components/data-grid'
import { Field, SelectField } from '@/components/records/fields'
import { NodePicker, type PickedNode } from '@/components/records/node-picker'
import {
  downloadUrl,
  type ProgressRow,
  useExportActions,
  useExports,
  useProgress,
} from './api'

const pct = (v: unknown) =>
  v === null || v === undefined ? '—' : `${Number(v).toFixed(1)} %`

function Verify({ projectId }: { projectId: number }) {
  const { t } = useTranslation()
  const { verify } = useExportActions(projectId)
  const [node, setNode] = useState<PickedNode | null>(null)
  const [qty, setQty] = useState('')
  const [inspection, setInspection] = useState('')
  return (
    <form
      className='grid gap-2 rounded-lg border p-3 sm:grid-cols-[2fr_1fr_1fr_auto] sm:items-end'
      onSubmit={(e) => {
        e.preventDefault()
        if (!node) return
        verify.mutate(
          {
            node_id: node.id,
            verified_qty: qty,
            inspection_id: inspection ? Number(inspection) : null,
          },
          { onSuccess: () => setQty('') }
        )
      }}
    >
      <Field label={t('p6.progress_unit')}>
        <NodePicker projectId={projectId} value={node} onChange={setNode} />
      </Field>
      <Field label={t('p6.verified_qty')}>
        <Input
          className='h-8'
          type='number'
          min='0'
          step='any'
          value={qty}
          onChange={(e) => setQty(e.target.value)}
          required
        />
      </Field>
      <Field label={t('p6.inspection_id')}>
        <Input
          className='h-8'
          type='number'
          min='1'
          value={inspection}
          onChange={(e) => setInspection(e.target.value)}
        />
      </Field>
      <Button type='submit' size='sm' disabled={!node || verify.isPending}>
        <CheckCheck className='size-4' />
        {t('p6.verify')}
      </Button>
      <p className='text-xs text-muted-foreground sm:col-span-4'>
        {t('p6.verify_hint')}
      </p>
    </form>
  )
}

/** Field checkout back to P6: verified progress per linked activity, exported for the scheduler. */
export function ExportTab({ projectId }: { projectId: number }) {
  const { t } = useTranslation()
  const session = useSession()
  const { data: rows = [] } = useProgress(projectId)
  const { data: history = [] } = useExports(projectId)
  const { create } = useExportActions(projectId)
  const [format, setFormat] = useState<'xer' | 'p6_xml' | 'csv'>('xer')
  const [onlyChanged, setOnlyChanged] = useState(true)

  const columns = useMemo<ColDef<ProgressRow>[]>(
    () => [
      {
        field: 'p6_activity_id',
        headerName: t('p6.activity_id'),
        width: 120,
        cellClass: 'font-mono',
      },
      { field: 'name', headerName: t('p6.name'), flex: 1, minWidth: 200 },
      {
        headerName: t('p6.nodes'),
        flex: 1,
        minWidth: 160,
        valueGetter: (p) => p.data?.nodes.join(', '),
      },
      {
        field: 'p6_percent',
        headerName: t('p6.p6_percent'),
        width: 100,
        type: 'rightAligned',
        valueFormatter: (p) => pct(p.value),
      },
      {
        field: 'reported_percent',
        headerName: t('p6.reported'),
        width: 100,
        type: 'rightAligned',
        valueFormatter: (p) => pct(p.value),
      },
      {
        field: 'verified_percent',
        headerName: t('p6.verified'),
        width: 100,
        type: 'rightAligned',
        cellClass: 'font-medium',
        valueFormatter: (p) => pct(p.value),
      },
      { field: 'actual_start', headerName: t('p6.actual_start'), width: 115 },
      { field: 'actual_finish', headerName: t('p6.actual_finish'), width: 115 },
      { field: 'status_code', headerName: t('p6.status'), width: 120 },
    ],
    [t]
  )

  return (
    <div className='flex flex-col gap-3'>
      {can(session, 'schedule.review') ? (
        <Verify projectId={projectId} />
      ) : null}
      {can(session, 'schedule.export') ? (
        <div className='flex flex-wrap items-end gap-3'>
          <Field label={t('p6.format')} className='w-44'>
            <SelectField
              value={format}
              onChange={(v) => setFormat((v as typeof format) ?? 'xer')}
              options={[
                { value: 'xer', label: 'XER update' },
                { value: 'p6_xml', label: 'P6 XML' },
                { value: 'csv', label: 'CSV' },
              ]}
            />
          </Field>
          <label className='flex items-center gap-2 pb-1.5 text-sm'>
            <Checkbox
              checked={onlyChanged}
              onCheckedChange={(v) => setOnlyChanged(v === true)}
            />
            {t('p6.only_changed')}
          </label>
          <Button
            size='sm'
            disabled={create.isPending}
            onClick={() => create.mutate({ format, only_changed: onlyChanged })}
          >
            <Download className='size-4' />
            {t('p6.export')}
          </Button>
        </div>
      ) : null}
      <p className='text-xs text-muted-foreground'>{t('p6.verified_only')}</p>
      <div className='h-[420px]'>
        <DataGrid<ProgressRow>
          rowData={rows}
          columnDefs={columns}
          getRowId={(p) => String(p.data.activity_id)}
        />
      </div>
      <section>
        <h3 className='mb-1 text-sm font-semibold'>{t('p6.history')}</h3>
        <ul className='grid gap-1 text-sm'>
          {history.map((e) => (
            <li key={e.id} className='flex items-center gap-2'>
              <span className='tabular-nums'>
                {new Date(e.created_at).toLocaleString()}
              </span>
              <span className='uppercase'>{e.format}</span>
              <span className='text-muted-foreground'>
                {t('p6.rows', { count: e.row_count })}
              </span>
              <a
                className='text-primary underline'
                href={downloadUrl(projectId, e.id)}
              >
                {t('p6.download')}
              </a>
            </li>
          ))}
        </ul>
      </section>
    </div>
  )
}
