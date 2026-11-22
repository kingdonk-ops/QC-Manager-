import { useMemo, useState } from 'react'
import type { ColDef } from 'ag-grid-community'
import { Upload } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { DataGrid } from '@/components/data-grid'
import { Field, Kpi, SelectField } from '@/components/records/fields'
import { NodePicker, type PickedNode } from '@/components/records/node-picker'
import { StatusBadge } from '@/components/records/status-badge'
import {
  type P6Change,
  type P6Import,
  useChanges,
  useImportActions,
  useImports,
  useUpload,
} from './api'
import { CHANGE_TYPES, describeChange, shiftLabel } from './helpers'

function Uploader({
  projectId,
  onDone,
}: {
  projectId: number
  onDone: (imp: P6Import) => void
}) {
  const { t } = useTranslation()
  const upload = useUpload(projectId)
  const [file, setFile] = useState<File | null>(null)
  const [createMissing, setCreateMissing] = useState(false)
  const [under, setUnder] = useState<PickedNode | null>(null)
  return (
    <form
      className='grid gap-3 rounded-lg border p-3 sm:grid-cols-[1fr_auto_1fr_auto] sm:items-end'
      onSubmit={(e) => {
        e.preventDefault()
        if (!file) return
        upload.mutate(
          { file, createMissing, createUnder: under?.id ?? null },
          { onSuccess: onDone }
        )
      }}
    >
      <Field label={t('p6.file')}>
        <Input
          type='file'
          accept='.xer,.xml'
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        />
      </Field>
      <label className='flex items-center gap-2 text-sm'>
        <Checkbox
          checked={createMissing}
          onCheckedChange={(v) => setCreateMissing(v === true)}
        />
        {t('p6.create_missing')}
      </label>
      <Field label={t('p6.create_under')}>
        <NodePicker
          projectId={projectId}
          value={under}
          onChange={setUnder}
          disabled={!createMissing}
        />
      </Field>
      <Button type='submit' disabled={!file || upload.isPending}>
        <Upload className='size-4' />
        {t('p6.preview')}
      </Button>
    </form>
  )
}

export function ImportTab({ projectId }: { projectId: number }) {
  const { t } = useTranslation()
  const { data: imports = [] } = useImports(projectId)
  const [selected, setSelected] = useState<number | undefined>()
  const current =
    imports.find((i) => i.id === selected) ??
    imports.find((i) => i.status === 'previewed') ??
    imports[0]
  const [kind, setKind] = useState('')
  const { data: changes = [] } = useChanges(projectId, current?.id)
  const { exclude, commit, discard } = useImportActions(projectId)
  const reviewing = current?.status === 'previewed'
  const shown = kind ? changes.filter((c) => c.change_type === kind) : changes
  const summary = (current?.summary ?? {}) as {
    activities?: number
    changes?: Record<string, number>
    matching?: Record<string, number>
    date_shifts?: { count: number; max_slip_days: number }
    linking?: Record<string, number>
    warnings?: string[]
  }

  const changed = Object.entries(summary.changes ?? {})
    .filter(([k]) => !['new', 'unchanged'].includes(k))
    .reduce((total, [, n]) => total + n, 0)

  const columns = useMemo<ColDef<P6Change>[]>(
    () => [
      {
        field: 'excluded',
        headerName: t('p6.apply'),
        width: 80,
        cellRenderer: (p: { data?: P6Change }) =>
          p.data ? (
            <Checkbox
              aria-label={t('p6.apply')}
              checked={!p.data.excluded}
              disabled={!reviewing}
              onCheckedChange={(v) =>
                exclude.mutate({
                  importId: p.data!.import_id,
                  changeId: p.data!.id,
                  excluded: v !== true,
                })
              }
            />
          ) : null,
      },
      {
        field: 'change_type',
        headerName: t('p6.change'),
        width: 160,
        cellRenderer: (p: { value?: string }) => (
          <StatusBadge status={p.value} />
        ),
      },
      {
        field: 'p6_activity_id',
        headerName: t('p6.activity_id'),
        width: 120,
        cellClass: 'font-mono',
      },
      { field: 'name', headerName: t('p6.name'), flex: 1, minWidth: 220 },
      {
        headerName: t('p6.detail'),
        flex: 1,
        minWidth: 240,
        valueGetter: (p) => (p.data ? describeChange(p.data) : ''),
      },
      {
        headerName: t('p6.shift'),
        width: 90,
        valueGetter: (p) => shiftLabel(p.data?.impact?.finish_shift_days),
        cellClass: (p) =>
          cn(
            'tabular-nums',
            Number(p.data?.impact?.finish_shift_days) > 0 && 'text-red-600'
          ),
      },
      {
        headerName: t('p6.impact'),
        flex: 1,
        minWidth: 200,
        valueGetter: (p) => {
          const impact = (p.data?.impact ?? {}) as {
            linked_nodes?: string[]
            relink_proposed?: string
            udf_notes?: string[]
          }
          return [
            ...(impact.linked_nodes ?? []),
            impact.relink_proposed
              ? `${t('p6.relink')} ${impact.relink_proposed}`
              : '',
            ...(impact.udf_notes ?? []),
          ]
            .filter(Boolean)
            .join('; ')
        },
      },
    ],
    [exclude, reviewing, t]
  )

  return (
    <div className='flex flex-col gap-3'>
      <Uploader projectId={projectId} onDone={(imp) => setSelected(imp.id)} />
      {imports.length > 0 ? (
        <div className='flex flex-wrap items-center gap-2 text-sm'>
          <span className='text-muted-foreground'>{t('p6.imports')}</span>
          {imports.map((i) => (
            <button
              key={i.id}
              type='button'
              onClick={() => setSelected(i.id)}
              className={cn(
                'rounded-md border px-2 py-1',
                current?.id === i.id && 'border-primary bg-accent'
              )}
            >
              #{i.id} {i.file_name} <StatusBadge status={i.status} />
            </button>
          ))}
        </div>
      ) : (
        <p className='text-sm text-muted-foreground'>{t('p6.no_imports')}</p>
      )}
      {current ? (
        <>
          <div className='grid grid-cols-2 gap-3 lg:grid-cols-5'>
            <Kpi label={t('p6.activities')} value={summary.activities ?? 0} />
            <Kpi
              label={t('p6.new_changed')}
              value={`${summary.changes?.new ?? 0} / ${changed}`}
            />
            <Kpi
              label={t('p6.removed')}
              value={summary.changes?.removed ?? 0}
              tone={summary.changes?.removed ? 'warn' : undefined}
            />
            <Kpi
              label={t('p6.date_shifts')}
              value={`${summary.date_shifts?.count ?? 0} (${shiftLabel(summary.date_shifts?.max_slip_days) || '0 d'})`}
            />
            <Kpi
              label={t('p6.matching')}
              value={`${(summary.matching?.matched ?? 0) + (summary.matching?.create ?? 0)} / ${summary.matching?.unmatched ?? 0} / ${summary.matching?.ineligible ?? 0}`}
            />
          </div>
          <p className='text-xs text-muted-foreground'>{t('p6.kpi_hint')}</p>
          {summary.warnings?.length ? (
            <ul className='list-disc ps-5 text-sm text-amber-700'>
              {summary.warnings.map((w) => (
                <li key={w}>{w}</li>
              ))}
            </ul>
          ) : null}
          <div className='flex flex-wrap items-center gap-2'>
            <div className='w-52'>
              <SelectField
                value={kind || null}
                onChange={(v) => setKind(v ?? '')}
                allowNone
                placeholder={t('p6.change')}
                options={CHANGE_TYPES.map((c) => ({
                  value: c,
                  label: c.replace(/_/g, ' '),
                }))}
              />
            </div>
            {reviewing ? (
              <>
                <Button
                  size='sm'
                  disabled={commit.isPending}
                  onClick={() => commit.mutate(current.id)}
                >
                  {t('p6.commit')}
                </Button>
                <Button
                  size='sm'
                  variant='outline'
                  onClick={() => discard.mutate(current.id)}
                >
                  {t('p6.discard')}
                </Button>
              </>
            ) : null}
            <span className='text-xs text-muted-foreground'>
              {t('p6.never_delete')}
            </span>
          </div>
          <div className='h-[480px]'>
            <DataGrid<P6Change>
              rowData={shown}
              columnDefs={columns}
              getRowId={(p) => String(p.data.id)}
            />
          </div>
        </>
      ) : null}
    </div>
  )
}
