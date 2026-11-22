import { useMemo, useState } from 'react'
import type { ColDef } from 'ag-grid-community'
import { FileText, RefreshCw } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { can, useSession } from '@/lib/session'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { DataGrid } from '@/components/data-grid'
import { Field } from '@/components/records/fields'
import { RecordSheet } from '@/components/records/record-sheet'
import { StatusBadge } from '@/components/records/status-badge'
import {
  type ClaimLine,
  claimLimit,
  MOVES,
  pdfUrl,
  useClaim,
  useClaimActions,
} from './api'

type Fmt = (v?: string | number | null) => string

function Summary({
  totals,
  format,
}: {
  totals: Record<string, string | number>
  format: Fmt
}) {
  const { t } = useTranslation()
  const rows: [string, string, boolean?][] = [
    ['works_to_date', t('claims.works_to_date')],
    ['variations_to_date', t('claims.variations_to_date')],
    ['gross_to_date', t('claims.gross_to_date'), true],
    ['retention_to_date', t('claims.less_retention')],
    ['net_to_date', t('claims.net_to_date'), true],
    ['previous_payments', t('claims.less_previous')],
    ['this_claim', t('claims.this_claim'), true],
  ]
  return (
    <table className='w-full max-w-md text-sm'>
      <tbody>
        {rows.map(([k, label, strong]) => (
          <tr key={k} className={strong ? 'border-t font-semibold' : ''}>
            <td className='py-1'>{label}</td>
            <td className='py-1 text-end tabular-nums'>{format(totals[k])}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function Moves({
  projectId,
  id,
  status,
}: {
  projectId: number
  id: number
  status: string
}) {
  const { t } = useTranslation()
  const session = useSession()
  const { move } = useClaimActions(projectId)
  const [amount, setAmount] = useState('')
  const [on, setOn] = useState('')
  const [reference, setReference] = useState('')
  const moves = (MOVES[status] ?? []).filter((m) => can(session, m.permission))
  if (!moves.length) return null
  const money = moves.some((m) => m.to === 'certified' || m.to === 'paid')
  return (
    <div className='flex flex-wrap items-end gap-2 rounded-lg border p-3'>
      {money ? (
        <>
          <Field label={t('claims.amount')} className='w-36'>
            <Input
              className='h-8'
              type='number'
              step='any'
              min='0'
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
            />
          </Field>
          <Field label={t('claims.on')} className='w-40'>
            <Input
              className='h-8'
              type='date'
              value={on}
              onChange={(e) => setOn(e.target.value)}
            />
          </Field>
          {status === 'submitted' ? (
            <Field label={t('claims.client_reference')} className='w-40'>
              <Input
                className='h-8'
                value={reference}
                onChange={(e) => setReference(e.target.value)}
              />
            </Field>
          ) : null}
        </>
      ) : null}
      {moves.map((m) => (
        <Button
          key={m.to}
          size='sm'
          variant={m.to === 'draft' ? 'outline' : 'default'}
          disabled={move.isPending}
          onClick={() =>
            move.mutate({ id, status: m.to, amount, on, reference })
          }
        >
          {t(`claims.move.${m.to}`)}
        </Button>
      ))}
    </div>
  )
}

/** The claim editor: lines valued from verified completion, editable down (never above) while drafting. */
export function ClaimSheet({
  projectId,
  id,
  onClose,
  format,
}: {
  projectId: number
  id: number
  onClose: () => void
  format: Fmt
}) {
  const { t } = useTranslation()
  const session = useSession()
  const { data: claim } = useClaim(projectId, id)
  const { reload, line, remove } = useClaimActions(projectId)
  const draft = claim?.status === 'draft' && can(session, 'claims.update')
  const money = (p: { value?: unknown }) =>
    format(p.value as string | number | null)
  const qty = (p: { value?: unknown }) =>
    p.value === null || p.value === undefined ? '' : String(Number(p.value))

  const columns = useMemo<ColDef<ClaimLine>[]>(
    () => [
      {
        field: 'kind',
        headerName: '',
        width: 90,
        valueFormatter: (p) => t(`claims.kind.${p.value}`),
      },
      { field: 'code', headerName: t('claims.code'), width: 120 },
      {
        field: 'description',
        headerName: t('claims.description'),
        flex: 1,
        minWidth: 180,
      },
      { field: 'unit', headerName: t('claims.unit'), width: 70 },
      {
        field: 'contract_qty',
        headerName: t('claims.contract_qty'),
        width: 100,
        type: 'rightAligned',
        valueFormatter: qty,
      },
      {
        field: 'rate',
        headerName: t('claims.rate'),
        width: 100,
        type: 'rightAligned',
        valueFormatter: money,
      },
      {
        field: 'verified_qty',
        headerName: t('claims.verified'),
        width: 95,
        type: 'rightAligned',
        valueFormatter: qty,
      },
      {
        field: 'previous_qty',
        headerName: t('claims.previous'),
        width: 95,
        type: 'rightAligned',
        valueFormatter: qty,
      },
      {
        field: 'to_date_qty',
        headerName: t('claims.to_date'),
        width: 95,
        type: 'rightAligned',
        valueFormatter: qty,
        editable: !!draft,
        cellClass: draft ? 'bg-amber-50 dark:bg-amber-950/30' : undefined,
      },
      {
        field: 'this_value',
        headerName: t('claims.this_period'),
        width: 120,
        type: 'rightAligned',
        valueFormatter: money,
      },
      {
        field: 'to_date_value',
        headerName: t('claims.value_to_date'),
        width: 120,
        type: 'rightAligned',
        valueFormatter: money,
      },
    ],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [draft, format, t]
  )

  if (!claim) return null
  return (
    <RecordSheet
      open
      onClose={onClose}
      wide
      title={`${claim.code} ${claim.period_start} – ${claim.period_end}`}
      badges={<StatusBadge status={claim.status} />}
      record={{ projectId, entityType: 'progress_claim', entityId: claim.id }}
    >
      <div className='grid gap-3 pt-2'>
        <div className='flex flex-wrap gap-2'>
          {draft ? (
            <Button
              size='sm'
              variant='outline'
              disabled={reload.isPending}
              onClick={() => reload.mutate(claim.id)}
            >
              <RefreshCw className='size-4' />
              {t('claims.refresh')}
            </Button>
          ) : null}
          {can(session, 'claims.export') ? (
            <Button size='sm' variant='outline' asChild>
              <a href={pdfUrl(claim.id)} target='_blank' rel='noreferrer'>
                <FileText className='size-4' />
                PDF
              </a>
            </Button>
          ) : null}
          {draft && can(session, 'claims.delete') ? (
            <Button
              size='sm'
              variant='outline'
              onClick={() => remove.mutate(claim.id, { onSuccess: onClose })}
            >
              {t('claims.delete')}
            </Button>
          ) : null}
        </div>
        <p className='text-xs text-muted-foreground'>
          {t('claims.verified_hint')}
        </p>
        <div className='h-[360px]'>
          <DataGrid<ClaimLine>
            rowData={claim.lines}
            columnDefs={columns}
            getRowId={(p) => String(p.data.id)}
            onCellValueChanged={(e) => {
              if (!e.data || e.colDef.field !== 'to_date_qty') return
              const value = Number(e.newValue)
              if (!Number.isFinite(value) || value < 0) return
              line.mutate({
                claimId: claim.id,
                lineId: e.data.id,
                qty: String(Math.min(value, claimLimit(e.data))),
              })
            }}
          />
        </div>
        <Summary
          totals={claim.totals as unknown as Record<string, string>}
          format={format}
        />
        {claim.certified_amount !== null ? (
          <p className='text-sm'>
            {t('claims.certified')}: {format(claim.certified_amount)}{' '}
            {claim.certified_on ?? ''} {claim.client_reference ?? ''}
            {claim.paid_amount !== null
              ? ` · ${t('claims.paid')}: ${format(claim.paid_amount)} ${claim.paid_on ?? ''}`
              : ''}
          </p>
        ) : null}
        <Moves projectId={projectId} id={claim.id} status={claim.status} />
      </div>
    </RecordSheet>
  )
}
