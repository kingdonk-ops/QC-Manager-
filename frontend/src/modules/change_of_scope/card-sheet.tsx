import { useState } from 'react'
import { Plus, Trash2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { can, useSession } from '@/lib/session'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Field, SelectField } from '@/components/records/fields'
import { NodePicker, type PickedNode } from '@/components/records/node-picker'
import { RecordSheet } from '@/components/records/record-sheet'
import { statusLabel } from '@/components/records/status'
import { StatusBadge } from '@/components/records/status-badge'
import {
  type Card,
  CHANGE_TYPES,
  lineAmount,
  MOVES,
  SOURCES,
  useCard,
  useCardActions,
  useHistory,
} from './api'

type LineDraft = {
  description: string
  quantity: string
  unit: string
  rate: string
  hours: string
}

const emptyLine = (): LineDraft => ({
  description: '',
  quantity: '1',
  unit: '',
  rate: '0',
  hours: '0',
})

type Draft = {
  title: string
  description: string
  source: string
  change_type: string
  node: PickedNode | null
  client_reference: string
  instructed_by: string
  instruction_date: string
  lines: LineDraft[]
}

function fromCard(card?: Card): Draft {
  return {
    title: card?.title ?? '',
    description: card?.description ?? '',
    source: card?.source ?? 'site_instruction',
    change_type: card?.change_type ?? 'scope_increase',
    node:
      card?.node_id && card.node_path
        ? { id: card.node_id, display_path: card.node_path }
        : null,
    client_reference: card?.client_reference ?? '',
    instructed_by: card?.instructed_by ?? '',
    instruction_date: card?.instruction_date ?? '',
    lines: (card?.lines ?? []).map((l) => ({
      description: l.description,
      quantity: String(l.quantity),
      unit: l.unit ?? '',
      rate: String(l.rate),
      hours: String(l.hours),
    })),
  }
}

function toBody(d: Draft) {
  return {
    title: d.title,
    description: d.description || null,
    source: d.source as never,
    change_type: d.change_type as never,
    node_id: d.node?.id ?? null,
    client_reference: d.client_reference || null,
    instructed_by: d.instructed_by || null,
    instruction_date: d.instruction_date || null,
    lines: d.lines
      .filter((l) => l.description.trim())
      .map((l) => ({
        description: l.description,
        quantity: l.quantity || '0',
        unit: l.unit || null,
        rate: l.rate || '0',
        hours: l.hours || '0',
      })),
  }
}

/** The card form: single column on a phone, so it works on site. */
function CardForm({
  projectId,
  draft,
  setDraft,
  editable,
  format,
}: {
  projectId: number
  draft: Draft
  setDraft: (d: Draft) => void
  editable: boolean
  format: (v: number) => string
}) {
  const { t } = useTranslation()
  const set = <K extends keyof Draft>(k: K, v: Draft[K]) =>
    setDraft({ ...draft, [k]: v })
  const setLine = (i: number, k: keyof LineDraft, v: string) =>
    set(
      'lines',
      draft.lines.map((l, n) => (n === i ? { ...l, [k]: v } : l))
    )
  const total = draft.lines.reduce((a, l) => a + lineAmount(l), 0)
  return (
    <div className='grid gap-3 sm:grid-cols-2'>
      <Field label={t('cos.title_field')} className='sm:col-span-2'>
        <Input
          value={draft.title}
          onChange={(e) => set('title', e.target.value)}
          disabled={!editable}
          required
        />
      </Field>
      <Field label={t('cos.change_type')}>
        <SelectField
          value={draft.change_type}
          onChange={(v) => set('change_type', v ?? 'scope_change')}
          options={CHANGE_TYPES.map((c) => ({
            value: c,
            label: t(`cos.type.${c}`),
          }))}
          disabled={!editable}
        />
      </Field>
      <Field label={t('cos.source')}>
        <SelectField
          value={draft.source}
          onChange={(v) => set('source', v ?? 'other')}
          options={SOURCES.map((s) => ({
            value: s,
            label: t(`cos.source.${s}`),
          }))}
          disabled={!editable}
        />
      </Field>
      <Field label={t('cos.location')} className='sm:col-span-2'>
        <NodePicker
          projectId={projectId}
          value={draft.node}
          onChange={(n) => set('node', n)}
          disabled={!editable}
        />
      </Field>
      <Field label={t('cos.client_reference')}>
        <Input
          value={draft.client_reference}
          onChange={(e) => set('client_reference', e.target.value)}
          disabled={!editable}
        />
      </Field>
      <Field label={t('cos.instructed_by')}>
        <Input
          value={draft.instructed_by}
          onChange={(e) => set('instructed_by', e.target.value)}
          disabled={!editable}
        />
      </Field>
      <Field label={t('cos.instruction_date')}>
        <Input
          type='date'
          value={draft.instruction_date}
          onChange={(e) => set('instruction_date', e.target.value)}
          disabled={!editable}
        />
      </Field>
      <Field label={t('cos.description_field')} className='sm:col-span-2'>
        <Textarea
          rows={3}
          value={draft.description}
          onChange={(e) => set('description', e.target.value)}
          disabled={!editable}
        />
      </Field>
      <div className='grid gap-2 sm:col-span-2'>
        <p className='text-xs text-muted-foreground'>{t('cos.estimate')}</p>
        {draft.lines.map((l, i) => (
          <div
            key={i}
            className='grid grid-cols-6 gap-1.5 rounded-md border p-2 sm:grid-cols-[3fr_1fr_1fr_1fr_1fr_auto]'
          >
            <Input
              className='col-span-6 h-8 sm:col-span-1'
              placeholder={t('cos.line_description')}
              value={l.description}
              onChange={(e) => setLine(i, 'description', e.target.value)}
              disabled={!editable}
            />
            <Input
              className='col-span-2 h-8 sm:col-span-1'
              type='number'
              step='any'
              min='0'
              aria-label={t('cos.qty')}
              placeholder={t('cos.qty')}
              value={l.quantity}
              onChange={(e) => setLine(i, 'quantity', e.target.value)}
              disabled={!editable}
            />
            <Input
              className='col-span-2 h-8 sm:col-span-1'
              aria-label={t('cos.unit')}
              placeholder={t('cos.unit')}
              value={l.unit}
              onChange={(e) => setLine(i, 'unit', e.target.value)}
              disabled={!editable}
            />
            <Input
              className='col-span-2 h-8 sm:col-span-1'
              type='number'
              step='any'
              min='0'
              aria-label={t('cos.rate')}
              placeholder={t('cos.rate')}
              value={l.rate}
              onChange={(e) => setLine(i, 'rate', e.target.value)}
              disabled={!editable}
            />
            <Input
              className='col-span-3 h-8 sm:col-span-1'
              type='number'
              step='any'
              min='0'
              aria-label={t('cos.hours')}
              placeholder={t('cos.hours')}
              value={l.hours}
              onChange={(e) => setLine(i, 'hours', e.target.value)}
              disabled={!editable}
            />
            {editable ? (
              <Button
                type='button'
                variant='ghost'
                size='icon'
                className='col-span-3 size-8 justify-self-end sm:col-span-1'
                aria-label={t('cos.remove_line')}
                onClick={() =>
                  set(
                    'lines',
                    draft.lines.filter((_, n) => n !== i)
                  )
                }
              >
                <Trash2 className='size-4' />
              </Button>
            ) : null}
          </div>
        ))}
        <div className='flex items-center justify-between'>
          {editable ? (
            <Button
              type='button'
              variant='outline'
              size='sm'
              onClick={() => set('lines', [...draft.lines, emptyLine()])}
            >
              <Plus className='size-4' />
              {t('cos.add_line')}
            </Button>
          ) : (
            <span />
          )}
          <span className='text-sm font-medium tabular-nums'>
            {t('cos.estimate_total')}: {format(total)}
          </span>
        </div>
      </div>
    </div>
  )
}

function History({ projectId, id }: { projectId: number; id: number }) {
  const { data = [] } = useHistory(projectId, id)
  return (
    <ul className='grid gap-1 text-sm'>
      {data.map((h, i) => (
        <li key={i} className='flex gap-2'>
          <span className='text-muted-foreground tabular-nums'>
            {h.changed_at
              ? new Date(String(h.changed_at)).toLocaleString()
              : ''}
          </span>
          <span>{statusLabel(String(h.to_status))}</span>
          {h.note ? (
            <span className='text-muted-foreground'>{String(h.note)}</span>
          ) : null}
        </li>
      ))}
    </ul>
  )
}

function Actions({ card, projectId }: { card: Card; projectId: number }) {
  const { t } = useTranslation()
  const session = useSession()
  const { move, convert } = useCardActions(projectId)
  const [note, setNote] = useState('')
  const [amount, setAmount] = useState(String(card.estimated_amount))
  const moves = (MOVES[card.status] ?? []).filter((m) =>
    can(session, m.permission)
  )
  const deciding = moves.some((m) => m.to === 'approved')
  return (
    <div className='grid gap-2 rounded-lg border p-3'>
      {card.expires_in_days !== null && card.expires_in_days !== undefined ? (
        <p className='text-sm text-amber-700'>
          {t('cos.expires_in', { count: Math.max(card.expires_in_days, 0) })}
        </p>
      ) : null}
      {moves.length ? (
        <Input
          className='h-8'
          placeholder={t('cos.note')}
          value={note}
          onChange={(e) => setNote(e.target.value)}
        />
      ) : null}
      {deciding ? (
        <Field label={t('cos.approved_amount')}>
          <Input
            className='h-8'
            type='number'
            step='any'
            min='0'
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
          />
        </Field>
      ) : null}
      <div className='flex flex-wrap gap-2'>
        {moves.map((m) => (
          <Button
            key={m.to}
            size='sm'
            variant={
              m.to === 'rejected' || m.to === 'withdrawn'
                ? 'outline'
                : 'default'
            }
            disabled={move.isPending}
            onClick={() =>
              move.mutate({
                id: card.id,
                status: m.to,
                note,
                approvedAmount: m.to === 'approved' ? amount : undefined,
              })
            }
          >
            {t(`cos.move.${m.to}`)}
          </Button>
        ))}
        {card.status === 'approved' &&
        can(session, 'change_of_scope.approve') ? (
          <Button
            size='sm'
            disabled={convert.isPending}
            onClick={() => convert.mutate(card.id)}
          >
            {t('cos.convert')}
          </Button>
        ) : null}
      </div>
      {card.change_order_code ? (
        <p className='text-sm'>
          {t('cos.converted_to')}{' '}
          <a
            className='text-primary underline'
            href={`/change-orders?project=${card.project_id}&co=${card.change_order_id}`}
          >
            {card.change_order_code}
          </a>
        </p>
      ) : null}
    </div>
  )
}

export function CardSheet({
  projectId,
  id,
  onClose,
  format,
}: {
  projectId: number
  id: number | 'new'
  onClose: () => void
  format: (v: number) => string
}) {
  const { t } = useTranslation()
  const session = useSession()
  const existing = useCard(projectId, id === 'new' ? undefined : id)
  const card = existing.data
  const { create, update, remove } = useCardActions(projectId)
  const [draft, setDraft] = useState<Draft | null>(null)
  if (id !== 'new' && !card) return null
  const current = draft ?? fromCard(card)
  const editable =
    id === 'new'
      ? can(session, 'change_of_scope.create')
      : card?.status === 'draft' && can(session, 'change_of_scope.update')

  const save = () => {
    const body = toBody(current)
    if (id === 'new') create.mutate(body, { onSuccess: onClose })
    else update.mutate({ id, body }, { onSuccess: () => setDraft(null) })
  }

  return (
    <RecordSheet
      open
      onClose={onClose}
      wide
      title={card ? `${card.code} ${card.title}` : t('cos.new')}
      subtitle={card?.work_anchor_path ?? card?.node_path ?? undefined}
      badges={card ? <StatusBadge status={card.status} /> : undefined}
      record={
        card
          ? { projectId, entityType: 'change_card', entityId: card.id }
          : undefined
      }
      tabs={
        card
          ? { History: <History projectId={projectId} id={card.id} /> }
          : undefined
      }
    >
      <form
        className='grid gap-3 pt-2'
        onSubmit={(e) => {
          e.preventDefault()
          save()
        }}
      >
        {card ? <Actions card={card} projectId={projectId} /> : null}
        <CardForm
          projectId={projectId}
          draft={current}
          setDraft={setDraft}
          editable={!!editable}
          format={format}
        />
        {editable ? (
          <div className='flex gap-2'>
            <Button
              type='submit'
              size='sm'
              disabled={create.isPending || update.isPending}
            >
              {id === 'new' ? t('cos.create') : t('common.save')}
            </Button>
            {card && can(session, 'change_of_scope.delete') ? (
              <Button
                type='button'
                size='sm'
                variant='outline'
                onClick={() => remove.mutate(card.id, { onSuccess: onClose })}
              >
                {t('cos.delete')}
              </Button>
            ) : null}
          </div>
        ) : null}
        {id === 'new' ? (
          <p className='text-xs text-muted-foreground'>
            {t('cos.photos_hint')}
          </p>
        ) : null}
      </form>
    </RecordSheet>
  )
}
