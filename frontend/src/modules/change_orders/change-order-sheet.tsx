import { useMemo, useState } from 'react'
import type { ColDef, ValueGetterParams } from 'ag-grid-community'
import { FileText, Plus, Trash2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { can, useSession } from '@/lib/session'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { DataGrid } from '@/components/data-grid'
import { Field, SelectField } from '@/components/records/fields'
import { RecordSheet } from '@/components/records/record-sheet'
import { statusLabel } from '@/components/records/status'
import { StatusBadge } from '@/components/records/status-badge'
import {
  CVR_APPLY,
  type ChangeOrderDetail,
  type ChangeOrderUpdate,
  type Line,
  pdfUrl,
  REASONS,
  SUBMITTER_MOVES,
  useChangeOrder,
  useCostHeadOptions,
  useDeleteChangeOrder,
  useLineMutations,
  useMoveChangeOrder,
  useUpdateChangeOrder,
} from './api'
import { DecisionDialog } from './decision-dialog'

type NumField =
  | 'original_quantity'
  | 'original_rate'
  | 'new_quantity'
  | 'new_rate'

const num = (v: unknown) => Number(v ?? 0) || 0
const round2 = (v: number) => Math.round(v * 100) / 100
const originalOf = (l: Line) =>
  round2(num(l.original_quantity) * num(l.original_rate))
const newOf = (l: Line) => round2(num(l.new_quantity) * num(l.new_rate))

function Header({
  co,
  projectId,
  editable,
}: {
  co: ChangeOrderDetail
  projectId: number
  editable: boolean
}) {
  const { t } = useTranslation()
  const update = useUpdateChangeOrder(projectId)
  const [draft, setDraft] = useState({
    title: co.title,
    reason: co.reason,
    description: co.description ?? '',
    request_date: co.request_date ?? '',
    time_impact_days: String(co.time_impact_days),
    cvr_apply: co.cvr_apply,
  })
  const set = (key: keyof typeof draft, value: string) =>
    setDraft((d) => ({ ...d, [key]: value }))

  return (
    <form
      className='grid gap-3 sm:grid-cols-3'
      onSubmit={(e) => {
        e.preventDefault()
        update.mutate({
          id: co.id,
          body: {
            ...draft,
            description: draft.description || null,
            request_date: draft.request_date || null,
            time_impact_days: Number(draft.time_impact_days) || 0,
          } as ChangeOrderUpdate,
        })
      }}
    >
      <Field label={t('co.title_field')} className='sm:col-span-3'>
        <Input
          value={draft.title}
          onChange={(e) => set('title', e.target.value)}
          disabled={!editable}
          required
        />
      </Field>
      <Field label={t('co.reason')}>
        <SelectField
          value={draft.reason}
          onChange={(v) => set('reason', v ?? 'other')}
          options={REASONS.map((r) => ({ value: r, label: t(`co.why.${r}`) }))}
          disabled={!editable}
        />
      </Field>
      <Field label={t('co.request_date')}>
        <Input
          type='date'
          value={draft.request_date}
          onChange={(e) => set('request_date', e.target.value)}
          disabled={!editable}
        />
      </Field>
      <Field label={t('co.time_impact')}>
        <Input
          type='number'
          value={draft.time_impact_days}
          onChange={(e) => set('time_impact_days', e.target.value)}
          disabled={!editable}
        />
      </Field>
      <Field label={t('co.description_field')} className='sm:col-span-2'>
        <Textarea
          rows={2}
          value={draft.description}
          onChange={(e) => set('description', e.target.value)}
          disabled={!editable}
        />
      </Field>
      <Field label={t('co.cvr_apply')}>
        <SelectField
          value={draft.cvr_apply}
          onChange={(v) => set('cvr_apply', v ?? 'none')}
          options={CVR_APPLY.map((c) => ({
            value: c,
            label: t(`co.apply.${c}`),
          }))}
          disabled={!editable}
        />
      </Field>
      {editable ? (
        <div className='sm:col-span-3'>
          <Button type='submit' size='sm' disabled={update.isPending}>
            {t('common.save')}
          </Button>
        </div>
      ) : null}
    </form>
  )
}

function Lines({
  co,
  projectId,
  editable,
  format,
}: {
  co: ChangeOrderDetail
  projectId: number
  editable: boolean
  format: (v?: string | number | null) => string
}) {
  const { t } = useTranslation()
  const session = useSession()
  const { data: heads = [] } = useCostHeadOptions(
    projectId,
    can(session, 'cvr.read')
  )
  const { add, update, remove } = useLineMutations(projectId, co.id)
  const [rows, setRows] = useState<Line[]>(co.lines)
  const [synced, setSynced] = useState(co.lines)
  if (synced !== co.lines) {
    setSynced(co.lines)
    setRows(co.lines)
  }
  const fmt = (p: { value?: unknown }) => format(p.value as number)

  const columns = useMemo<ColDef<Line>[]>(() => {
    const headNames = Object.fromEntries(
      heads.map((h) => [String(h.id), `${h.code} ${h.description}`])
    )
    const numCol = (field: NumField, headerName: string): ColDef<Line> => ({
      field,
      headerName,
      type: 'rightAligned',
      editable: (p) => editable && !p.node.rowPinned,
      width: 105,
      cellClass: 'tabular-nums',
      valueParser: (p) => {
        const n = Number(String(p.newValue).replace(/[^0-9.-]/g, ''))
        return Number.isFinite(n) ? String(n) : p.oldValue
      },
    })
    const computed = (
      headerName: string,
      get: (l: Line) => number,
      delta?: boolean
    ): ColDef<Line> => ({
      headerName,
      type: 'rightAligned',
      width: 120,
      valueGetter: (p: ValueGetterParams<Line>) =>
        p.data ? (p.node?.rowPinned ? null : get(p.data)) : null,
      valueFormatter: fmt,
      cellClass: (p) =>
        cn(
          'tabular-nums',
          delta && 'font-medium',
          delta && Number(p.value) < 0 && 'text-red-600',
          delta && Number(p.value) > 0 && 'text-green-600'
        ),
    })
    return [
      {
        field: 'description',
        headerName: t('co.line_description'),
        editable: (p) => editable && !p.node.rowPinned,
        flex: 1,
        minWidth: 200,
      },
      {
        field: 'cost_head_id',
        headerName: t('co.cost_head'),
        width: 150,
        editable: (p) => editable && !p.node.rowPinned && heads.length > 0,
        cellEditor: 'agSelectCellEditor',
        cellEditorParams: { values: ['', ...heads.map((h) => String(h.id))] },
        refData: headNames,
        valueGetter: (p) =>
          p.data?.cost_head_id != null ? String(p.data.cost_head_id) : '',
        valueSetter: (p) => {
          if (!p.data) return false
          p.data.cost_head_id = p.newValue ? Number(p.newValue) : null
          return true
        },
      },
      {
        field: 'cost_code',
        headerName: t('co.cost_code'),
        width: 100,
        editable: (p) => editable && !p.node.rowPinned,
      },
      {
        field: 'unit',
        headerName: t('co.unit'),
        width: 70,
        editable: (p) => editable && !p.node.rowPinned,
      },
      numCol('original_quantity', t('co.orig_qty')),
      numCol('original_rate', t('co.orig_rate')),
      computed(t('co.orig_amount'), originalOf),
      numCol('new_quantity', t('co.new_qty')),
      numCol('new_rate', t('co.new_rate')),
      computed(t('co.new_amount'), newOf),
      {
        ...computed(t('co.delta'), (l) => newOf(l) - originalOf(l), true),
        valueGetter: (p: ValueGetterParams<Line>) =>
          p.data
            ? p.node?.rowPinned
              ? num(p.data.delta)
              : newOf(p.data) - originalOf(p.data)
            : null,
      },
      ...(editable
        ? [
            {
              headerName: '',
              width: 44,
              sortable: false,
              filter: false,
              cellRenderer: (p: {
                data?: Line
                node: { rowPinned?: string | null }
              }) =>
                p.data && !p.node.rowPinned ? (
                  <button
                    className='text-muted-foreground hover:text-red-600'
                    aria-label={t('co.delete_line')}
                    onClick={() => remove.mutate(p.data!.id)}
                  >
                    <Trash2 className='size-4' />
                  </button>
                ) : null,
            } satisfies ColDef<Line>,
          ]
        : []),
    ]
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editable, heads, t, format])

  const totals = useMemo(() => {
    const original = rows.reduce((s, l) => s + originalOf(l), 0)
    const next = rows.reduce((s, l) => s + newOf(l), 0)
    return [
      {
        id: -1,
        change_order_id: co.id,
        description: t('common.total'),
        sort_order: 0,
        cost_head_id: null,
        cost_code: null,
        unit: null,
        original_quantity: '0',
        original_rate: '0',
        new_quantity: '0',
        new_rate: '0',
        original_amount: String(original),
        new_amount: String(next),
        delta: String(round2(next - original)),
      } as Line,
    ]
  }, [rows, co.id, t])

  return (
    <div className='space-y-2'>
      <div className='h-[300px]'>
        <DataGrid<Line>
          rowData={rows}
          columnDefs={columns}
          getRowId={(p) => String(p.data.id)}
          pinnedBottomRowData={totals}
          getRowClass={(p) =>
            p.node.rowPinned ? 'font-semibold bg-muted' : undefined
          }
          singleClickEdit
          onCellValueChanged={(e) => {
            if (!e.data || e.node.rowPinned || e.newValue === e.oldValue) return
            const field = e.colDef.field
            if (!field) return
            setRows((r) =>
              r.map((l) => (l.id === e.data.id ? { ...e.data } : l))
            )
            const value =
              field === 'cost_head_id'
                ? e.data.cost_head_id
                : e.newValue === ''
                  ? null
                  : (e.newValue as string)
            update.mutate({ id: e.data.id, field, value })
          }}
        />
      </div>
      {editable ? (
        <Button
          size='sm'
          variant='outline'
          disabled={add.isPending}
          onClick={() => add.mutate({ description: t('co.new_line') })}
        >
          <Plus /> {t('co.add_line')}
        </Button>
      ) : null}
    </div>
  )
}

function History({ co }: { co: ChangeOrderDetail }) {
  const { t } = useTranslation()
  return (
    <dl className='grid grid-cols-[10rem_1fr] gap-y-1 text-sm'>
      <dt className='text-muted-foreground'>{t('co.requested_by')}</dt>
      <dd>{co.requested_by_name ?? '—'}</dd>
      <dt className='text-muted-foreground'>{t('co.submitted_at')}</dt>
      <dd>
        {co.submitted_at ? new Date(co.submitted_at).toLocaleString() : '—'}
      </dd>
      <dt className='text-muted-foreground'>{t('co.approver')}</dt>
      <dd>{co.approver_name ?? '—'}</dd>
      <dt className='text-muted-foreground'>{t('co.decided_on')}</dt>
      <dd>{co.decided_on ?? '—'}</dd>
      <dt className='text-muted-foreground'>{t('co.decision_comment')}</dt>
      <dd>{co.decision_comment ?? '—'}</dd>
      <dt className='text-muted-foreground'>{t('co.applied_to_cvr')}</dt>
      <dd>
        {co.applied_to_cvr_at
          ? new Date(co.applied_to_cvr_at).toLocaleString()
          : '—'}
      </dd>
    </dl>
  )
}

export function ChangeOrderSheet({
  projectId,
  id,
  onClose,
  format,
}: {
  projectId: number
  id: number
  onClose: () => void
  format: (v?: string | number | null) => string
}) {
  const { t } = useTranslation()
  const session = useSession()
  const { data: co } = useChangeOrder(projectId, id)
  const move = useMoveChangeOrder(projectId)
  const remove = useDeleteChangeOrder(projectId)
  const [deciding, setDeciding] = useState(false)
  if (!co) return null

  const editable = co.status === 'draft' && can(session, 'change_orders.update')
  const approver = can(session, 'change_orders.approve')
  const submitter = can(session, 'change_orders.submit')
  const pending = co.status === 'submitted' || co.status === 'under_review'

  return (
    <RecordSheet
      open
      onClose={onClose}
      wide
      title={`${co.code} · ${co.title}`}
      subtitle={`${t('co.delta')}: ${format(co.total_delta)} · ${co.time_impact_days} ${t('co.days')}`}
      badges={
        <>
          <StatusBadge status={co.status} />
          <StatusBadge status={co.reason} />
        </>
      }
      record={{ projectId, entityType: 'change_order', entityId: co.id }}
      tabs={{ [t('co.approval')]: <History co={co} /> }}
    >
      <div className='space-y-4'>
        <Header
          key={co.status}
          co={co}
          projectId={projectId}
          editable={editable}
        />
        <Lines
          co={co}
          projectId={projectId}
          editable={editable}
          format={format}
        />
        <div className='flex flex-wrap items-center gap-2'>
          {submitter
            ? (SUBMITTER_MOVES[co.status] ?? []).map((s) => (
                <Button
                  key={s}
                  size='sm'
                  variant={s === 'submitted' ? 'default' : 'outline'}
                  disabled={move.isPending}
                  onClick={() => move.mutate({ id: co.id, status: s })}
                >
                  {t(`co.move.${s}`)}
                </Button>
              ))
            : null}
          {approver && co.status === 'submitted' ? (
            <Button
              size='sm'
              variant='outline'
              onClick={() => move.mutate({ id: co.id, status: 'under_review' })}
            >
              {t('co.move.under_review')}
            </Button>
          ) : null}
          {approver && pending ? (
            <Button size='sm' onClick={() => setDeciding(true)}>
              {t('co.decide')}
            </Button>
          ) : null}
          <Button size='sm' variant='outline' asChild>
            <a href={pdfUrl(co.id)} target='_blank' rel='noreferrer'>
              <FileText /> PDF
            </a>
          </Button>
          {can(session, 'change_orders.delete') &&
          !pending &&
          co.status !== 'approved' ? (
            <Button
              size='sm'
              variant='ghost'
              className='ms-auto text-red-600'
              onClick={() => remove.mutate(co.id, { onSuccess: onClose })}
            >
              <Trash2 /> {t('co.delete')}
            </Button>
          ) : null}
        </div>
        <p className='text-xs text-muted-foreground'>
          {statusLabel(co.status)} · {t('co.lines_locked_hint')}
        </p>
      </div>
      <DecisionDialog
        open={deciding}
        onClose={() => setDeciding(false)}
        co={co}
        format={format}
        onDecide={(status, comment) =>
          move.mutate(
            { id: co.id, status, comment },
            { onSuccess: () => setDeciding(false) }
          )
        }
        pending={move.isPending}
      />
    </RecordSheet>
  )
}
