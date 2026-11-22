import { useMemo, useState } from 'react'
import type { ColDef, ValueGetterParams } from 'ag-grid-community'
import {
  Ban,
  FileText,
  Lock,
  PackageCheck,
  Plus,
  Send,
  Trash2,
} from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { can, useSession } from '@/lib/session'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { DataGrid } from '@/components/data-grid'
import { Attachments } from '@/components/records/attachments'
import { Field, SelectField } from '@/components/records/fields'
import { RecordSheet } from '@/components/records/record-sheet'
import { StatusBadge } from '@/components/records/status-badge'
import {
  type PoLine,
  type PurchaseOrderDetail,
  type PurchaseOrderUpdate,
  pdfUrl,
  useCompanies,
  useCompanyContacts,
  useLineMutations,
  usePoActions,
  usePurchaseOrder,
  useUpdatePurchaseOrder,
} from './api'
import { ReceiptDialog } from './receipt-dialog'
import { SendDialog } from './send-dialog'

type Format = (v?: string | number | null) => string

const num = (v: unknown) => Number(v ?? 0) || 0
const round2 = (v: number) => Math.round(v * 100) / 100
const amountOf = (l: PoLine) => round2(num(l.quantity) * num(l.unit_price))
const taxOf = (l: PoLine) => round2((amountOf(l) * num(l.tax_rate)) / 100)

function SupplierPanel({ po }: { po: PurchaseOrderDetail }) {
  const { t } = useTranslation()
  const s = po.supplier
  if (!s || (!s.company_id && !s.contact_id))
    return (
      <p className='text-sm text-muted-foreground'>{t('po.no_supplier')}</p>
    )
  const banking = Object.entries(s.banking ?? {})
  return (
    <div className='grid gap-x-4 gap-y-1 rounded-md border p-3 text-sm sm:grid-cols-2'>
      <div>
        <p className='font-medium'>{s.company_name ?? s.contact_name}</p>
        {s.address ? <p className='whitespace-pre-line'>{s.address}</p> : null}
        {s.email ? <p className='text-muted-foreground'>{s.email}</p> : null}
        {s.phone ? <p className='text-muted-foreground'>{s.phone}</p> : null}
        {s.tax_id ? (
          <p className='text-muted-foreground'>
            {t('po.tax_id')}: {s.tax_id}
          </p>
        ) : null}
        {s.contact_name ? (
          <p className='pt-1'>
            {t('po.attention')}: {s.contact_name}
            {s.contact_email ? ` · ${s.contact_email}` : ''}
          </p>
        ) : null}
      </div>
      <div>
        <p className='text-xs font-medium text-muted-foreground'>
          {t('po.banking')}
        </p>
        {banking.length ? (
          <dl className='grid grid-cols-[auto_1fr] gap-x-2'>
            {banking.map(([k, v]) => (
              <div key={k} className='contents'>
                <dt className='text-muted-foreground'>
                  {k.replace(/_/g, ' ')}
                </dt>
                <dd className='font-mono'>{String(v)}</dd>
              </div>
            ))}
          </dl>
        ) : (
          <p className='text-muted-foreground'>—</p>
        )}
      </div>
    </div>
  )
}

function Header({
  po,
  projectId,
  editable,
}: {
  po: PurchaseOrderDetail
  projectId: number
  editable: boolean
}) {
  const { t } = useTranslation()
  const update = useUpdatePurchaseOrder(projectId, po.id)
  const [draft, setDraft] = useState({
    title: po.title ?? '',
    supplier_company_id: po.supplier_company_id,
    supplier_contact_id: po.supplier_contact_id,
    order_date: po.order_date ?? '',
    required_by: po.required_by ?? '',
    delivery_address: po.delivery_address ?? '',
    currency: po.currency,
    terms: po.terms ?? '',
    notes: po.notes ?? '',
    approval_threshold:
      po.approval_threshold != null ? String(po.approval_threshold) : '',
  })
  const { data: companies = [] } = useCompanies('')
  const { data: contacts = [] } = useCompanyContacts(draft.supplier_company_id)
  const set = <K extends keyof typeof draft>(
    key: K,
    value: (typeof draft)[K]
  ) => setDraft((d) => ({ ...d, [key]: value }))
  const companyOptions = companies.map((c) => ({
    value: String(c.id),
    label: c.name,
  }))
  if (
    po.supplier_company_id &&
    !companies.some((c) => c.id === po.supplier_company_id)
  )
    companyOptions.push({
      value: String(po.supplier_company_id),
      label: po.supplier?.company_name ?? `#${po.supplier_company_id}`,
    })

  return (
    <form
      className='grid gap-3 sm:grid-cols-3'
      onSubmit={(e) => {
        e.preventDefault()
        update.mutate({
          ...draft,
          title: draft.title || null,
          order_date: draft.order_date || null,
          required_by: draft.required_by || null,
          delivery_address: draft.delivery_address || null,
          terms: draft.terms || null,
          notes: draft.notes || null,
          approval_threshold: draft.approval_threshold || null,
        } as PurchaseOrderUpdate)
      }}
    >
      <Field label={t('po.supplier')}>
        <SelectField
          value={
            draft.supplier_company_id ? String(draft.supplier_company_id) : null
          }
          onChange={(v) => {
            set('supplier_company_id', v ? Number(v) : null)
            set('supplier_contact_id', null)
          }}
          options={companyOptions}
          allowNone
          disabled={!editable}
        />
      </Field>
      <Field label={t('po.contact')}>
        <SelectField
          value={
            draft.supplier_contact_id ? String(draft.supplier_contact_id) : null
          }
          onChange={(v) => set('supplier_contact_id', v ? Number(v) : null)}
          options={[
            ...contacts.map((c) => ({
              value: String(c.id),
              label: c.email ? `${c.full_name} · ${c.email}` : c.full_name,
            })),
            ...(po.supplier_contact_id &&
            !contacts.some((c) => c.id === po.supplier_contact_id)
              ? [
                  {
                    value: String(po.supplier_contact_id),
                    label:
                      po.supplier?.contact_name ?? `#${po.supplier_contact_id}`,
                  },
                ]
              : []),
          ]}
          allowNone
          disabled={!editable}
        />
      </Field>
      <Field label={t('po.reference')}>
        <Input
          value={draft.title}
          onChange={(e) => set('title', e.target.value)}
          disabled={!editable}
        />
      </Field>
      <Field label={t('po.order_date')}>
        <Input
          type='date'
          value={draft.order_date}
          onChange={(e) => set('order_date', e.target.value)}
          disabled={!editable}
        />
      </Field>
      <Field label={t('po.required_by')}>
        <Input
          type='date'
          value={draft.required_by}
          onChange={(e) => set('required_by', e.target.value)}
          disabled={!editable}
        />
      </Field>
      <div className='grid grid-cols-2 gap-3'>
        <Field label={t('po.currency')}>
          <Input
            value={draft.currency}
            maxLength={3}
            onChange={(e) => set('currency', e.target.value.toUpperCase())}
            disabled={!editable}
          />
        </Field>
        <Field label={t('po.threshold')}>
          <Input
            type='number'
            min={0}
            step='0.01'
            value={draft.approval_threshold}
            onChange={(e) => set('approval_threshold', e.target.value)}
            disabled={!editable}
          />
        </Field>
      </div>
      <Field label={t('po.delivery_address')}>
        <Textarea
          rows={2}
          value={draft.delivery_address}
          onChange={(e) => set('delivery_address', e.target.value)}
          disabled={!editable}
        />
      </Field>
      <Field label={t('po.terms')}>
        <Textarea
          rows={2}
          value={draft.terms}
          onChange={(e) => set('terms', e.target.value)}
          disabled={!editable}
        />
      </Field>
      <Field label={t('po.notes')}>
        <Textarea
          rows={2}
          value={draft.notes}
          onChange={(e) => set('notes', e.target.value)}
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
  po,
  projectId,
  editable,
  format,
}: {
  po: PurchaseOrderDetail
  projectId: number
  editable: boolean
  format: Format
}) {
  const { t } = useTranslation()
  const { add, update, remove } = useLineMutations(projectId, po.id)
  const source = po.lines ?? []
  const [rows, setRows] = useState<PoLine[]>(source)
  const [synced, setSynced] = useState(source)
  if (synced !== source) {
    setSynced(source)
    setRows(source)
  }
  const fmt = (p: { value?: unknown }) => format(p.value as number)

  const columns = useMemo<ColDef<PoLine>[]>(() => {
    const canEdit = (p: { node: { rowPinned?: string | null } }) =>
      editable && !p.node.rowPinned
    const numeric = (
      field: 'quantity' | 'unit_price' | 'tax_rate',
      headerName: string
    ) =>
      ({
        field,
        headerName,
        type: 'rightAligned',
        editable: canEdit,
        width: field === 'tax_rate' ? 80 : 110,
        cellClass: 'tabular-nums',
        valueFormatter: (p) =>
          p.node?.rowPinned
            ? ''
            : field === 'unit_price'
              ? fmt(p)
              : String(Number(p.value ?? 0)),
        valueParser: (p) => {
          const n = Number(String(p.newValue).replace(/[^0-9.-]/g, ''))
          return Number.isFinite(n) && n >= 0 ? String(n) : p.oldValue
        },
      }) satisfies ColDef<PoLine>
    const computed = (
      headerName: string,
      get: (l: PoLine) => number,
      total: keyof PoLine
    ) =>
      ({
        headerName,
        type: 'rightAligned',
        width: 120,
        valueGetter: (p: ValueGetterParams<PoLine>) =>
          p.data
            ? p.node?.rowPinned
              ? num(p.data[total])
              : get(p.data)
            : null,
        valueFormatter: fmt,
        cellClass: 'tabular-nums',
      }) satisfies ColDef<PoLine>
    return [
      {
        field: 'description',
        headerName: t('po.item'),
        editable: canEdit,
        flex: 1,
        minWidth: 200,
      },
      { field: 'unit', headerName: t('po.unit'), editable: canEdit, width: 70 },
      numeric('quantity', t('po.qty')),
      numeric('unit_price', t('po.unit_price')),
      numeric('tax_rate', t('po.tax_pct')),
      computed(t('po.amount'), amountOf, 'amount'),
      computed(t('po.tax'), taxOf, 'tax'),
      {
        field: 'cost_code',
        headerName: t('po.cost_code'),
        editable: canEdit,
        width: 100,
      },
      {
        field: 'received_quantity',
        headerName: t('po.received'),
        type: 'rightAligned',
        width: 95,
        valueFormatter: (p) =>
          p.node?.rowPinned ? '' : String(Number(p.value ?? 0)),
        cellClass: (p) =>
          num(p.data?.received_quantity) > num(p.data?.quantity)
            ? 'text-amber-600'
            : '',
      },
      ...(editable
        ? [
            {
              headerName: '',
              width: 44,
              sortable: false,
              filter: false,
              cellRenderer: (p: {
                data?: PoLine
                node: { rowPinned?: string | null }
              }) =>
                p.data && !p.node.rowPinned ? (
                  <button
                    className='text-muted-foreground hover:text-red-600'
                    aria-label={t('po.delete_line')}
                    onClick={() => remove.mutate(p.data!.id)}
                  >
                    <Trash2 className='size-4' />
                  </button>
                ) : null,
            } satisfies ColDef<PoLine>,
          ]
        : []),
    ]
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editable, t, format])

  const totals = useMemo(() => {
    const net = rows.reduce((s, l) => s + amountOf(l), 0)
    const tax = rows.reduce((s, l) => s + taxOf(l), 0)
    return [
      {
        id: -1,
        purchase_order_id: po.id,
        description: `${t('common.total')} · ${t('po.gross')} ${format(net + tax)}`,
        sort_order: 0,
        unit: null,
        quantity: '0',
        unit_price: '0',
        tax_rate: '0',
        amount: String(round2(net)),
        tax: String(round2(tax)),
        cost_code: null,
        cost_head_id: null,
        received_quantity: '0',
      } as PoLine,
    ]
  }, [rows, po.id, t, format])

  return (
    <div className='space-y-2'>
      <div className='h-[280px]'>
        <DataGrid<PoLine>
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
            update.mutate({
              id: e.data.id,
              field,
              value: e.newValue === '' ? null : String(e.newValue),
            })
          }}
        />
      </div>
      {editable ? (
        <Button
          size='sm'
          variant='outline'
          disabled={add.isPending}
          onClick={() => add.mutate({ description: t('po.new_item') })}
        >
          <Plus /> {t('po.add_line')}
        </Button>
      ) : null}
    </div>
  )
}

function Receipts({
  po,
  projectId,
}: {
  po: PurchaseOrderDetail
  projectId: number
}) {
  const { t } = useTranslation()
  const receipts = po.receipts ?? []
  if (!receipts.length)
    return (
      <p className='text-sm text-muted-foreground'>{t('po.no_receipts')}</p>
    )
  return (
    <div className='space-y-4'>
      {receipts.map((r) => (
        <div key={r.id} className='space-y-2 rounded-md border p-3 text-sm'>
          <p className='font-medium'>
            {r.code} · {r.received_date}
            {r.received_by_name ? ` · ${r.received_by_name}` : ''}
          </p>
          <ul className='list-inside list-disc'>
            {r.lines.map((l) => (
              <li key={l.line_id}>
                {Number(l.quantity)} {l.unit ?? ''} {l.description}
              </li>
            ))}
          </ul>
          {r.quality_notes ? (
            <p className='text-muted-foreground'>{r.quality_notes}</p>
          ) : null}
          <Attachments
            projectId={projectId}
            entityType='goods_receipt'
            entityId={r.id}
          />
        </div>
      ))}
    </div>
  )
}

export function PoSheet({
  projectId,
  id,
  onClose,
  format,
}: {
  projectId: number
  id: number
  onClose: () => void
  format: Format
}) {
  const { t } = useTranslation()
  const session = useSession()
  const { data: po } = usePurchaseOrder(projectId, id)
  const actions = usePoActions(projectId, id)
  const [dialog, setDialog] = useState<'send' | 'receive'>()
  if (!po) return null

  const editable = po.status === 'draft' && can(session, 'procurement.update')
  const sendable = ['draft', 'sent', 'partially_received'].includes(po.status)
  const receivable = ['sent', 'partially_received', 'fully_received'].includes(
    po.status
  )

  return (
    <RecordSheet
      open
      onClose={onClose}
      wide
      title={`${po.code}${po.title ? ` · ${po.title}` : ''}`}
      subtitle={`${po.supplier_name ?? t('po.no_supplier')} · ${t('po.gross')} ${po.currency} ${format(po.gross_total)}`}
      badges={
        <>
          <StatusBadge status={po.status} />
          {po.overdue ? <StatusBadge status='overdue' /> : null}
          {po.needs_approval ? <StatusBadge status='pending' /> : null}
        </>
      }
      record={{ projectId, entityType: 'purchase_order', entityId: po.id }}
      tabs={{
        [`${t('po.receipts')} (${po.receipts?.length ?? 0})`]: (
          <Receipts po={po} projectId={projectId} />
        ),
      }}
    >
      <div className='space-y-4'>
        <SupplierPanel po={po} />
        <Header
          key={po.status}
          po={po}
          projectId={projectId}
          editable={editable}
        />
        <Lines
          po={po}
          projectId={projectId}
          editable={editable}
          format={format}
        />
        <div className='grid grid-cols-2 gap-2 text-sm sm:grid-cols-4'>
          <span>
            {t('po.net')}:{' '}
            <b className='tabular-nums'>{format(po.net_total)}</b>
          </span>
          <span>
            {t('po.tax')}:{' '}
            <b className='tabular-nums'>{format(po.tax_total)}</b>
          </span>
          <span>
            {t('po.received_value')}:{' '}
            <b className='tabular-nums'>{format(po.received_net)}</b> (
            {po.received_pct}%)
          </span>
          <span>
            {t('po.outstanding')}:{' '}
            <b className='tabular-nums'>{format(po.outstanding_net)}</b>
          </span>
        </div>
        <div className='flex flex-wrap items-center gap-2'>
          {sendable && can(session, 'procurement.submit') ? (
            <Button size='sm' onClick={() => setDialog('send')}>
              <Send /> {po.status === 'draft' ? t('po.send') : t('po.resend')}
            </Button>
          ) : null}
          {receivable && can(session, 'procurement.transition') ? (
            <Button
              size='sm'
              variant='outline'
              onClick={() => setDialog('receive')}
            >
              <PackageCheck /> {t('po.receive')}
            </Button>
          ) : null}
          <Button size='sm' variant='outline' asChild>
            <a href={pdfUrl(po.id)} target='_blank' rel='noreferrer'>
              <FileText /> PDF
            </a>
          </Button>
          {can(session, 'procurement.transition') &&
          ['sent', 'partially_received', 'fully_received'].includes(
            po.status
          ) ? (
            <Button
              size='sm'
              variant='outline'
              onClick={() => actions.status.mutate('closed')}
            >
              <Lock /> {t('po.close')}
            </Button>
          ) : null}
          {can(session, 'procurement.transition') &&
          ['draft', 'sent'].includes(po.status) ? (
            <Button
              size='sm'
              variant='ghost'
              onClick={() => actions.status.mutate('cancelled')}
            >
              <Ban /> {t('po.cancel_po')}
            </Button>
          ) : null}
          {can(session, 'procurement.delete') &&
          ['draft', 'cancelled'].includes(po.status) ? (
            <Button
              size='sm'
              variant='ghost'
              className='ms-auto text-red-600'
              onClick={() =>
                actions.remove.mutate(undefined, { onSuccess: onClose })
              }
            >
              <Trash2 /> {t('po.delete')}
            </Button>
          ) : null}
        </div>
      </div>
      {dialog === 'send' ? (
        <SendDialog
          po={po}
          projectId={projectId}
          open
          onClose={() => setDialog(undefined)}
          format={format}
        />
      ) : null}
      {dialog === 'receive' ? (
        <ReceiptDialog
          po={po}
          projectId={projectId}
          open
          onClose={() => setDialog(undefined)}
        />
      ) : null}
    </RecordSheet>
  )
}
