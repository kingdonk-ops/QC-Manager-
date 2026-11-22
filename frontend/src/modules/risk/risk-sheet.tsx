import { useState } from 'react'
import { usePeople } from '@/modules/people/api'
import { Trash2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { can, useSession } from '@/lib/session'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Field, SelectField } from '@/components/records/fields'
import { RecordSheet } from '@/components/records/record-sheet'
import { statusLabel } from '@/components/records/status'
import { StatusBadge } from '@/components/records/status-badge'
import {
  CATEGORIES,
  IMPACTS,
  NEXT_STATUS,
  PROBABILITIES,
  RESPONSES,
  type Risk,
  type RiskUpdate,
  useDeleteRisk,
  useRiskHistory,
  useRiskStatus,
  useSaveRisk,
} from './api'

type Draft = {
  title: string
  description: string
  category: string
  cause: string
  effect: string
  probability: string
  impact: string
  cost_impact: string
  schedule_impact_days: string
  owner_id: number | null
  mitigation: string
  contingency: string
  residual_probability: string | null
  residual_impact: string | null
  response: string | null
  review_date: string
}

const fromRisk = (r?: Risk): Draft => ({
  title: r?.title ?? '',
  description: r?.description ?? '',
  category: r?.category ?? 'technical',
  cause: r?.cause ?? '',
  effect: r?.effect ?? '',
  probability: r ? Number(r.probability).toFixed(1) : '0.5',
  impact: r?.impact ?? 'medium',
  cost_impact: r ? String(r.cost_impact) : '0',
  schedule_impact_days: String(r?.schedule_impact_days ?? 0),
  owner_id: r?.owner_id ?? null,
  mitigation: r?.mitigation ?? '',
  contingency: r?.contingency ?? '',
  residual_probability:
    r?.residual_probability != null
      ? Number(r.residual_probability).toFixed(1)
      : null,
  residual_impact: r?.residual_impact ?? null,
  response: r?.response ?? null,
  review_date: r?.review_date ?? '',
})

const toBody = (d: Draft): RiskUpdate =>
  ({
    title: d.title,
    description: d.description || null,
    category: d.category,
    cause: d.cause || null,
    effect: d.effect || null,
    probability: d.probability,
    impact: d.impact,
    cost_impact: d.cost_impact || '0',
    schedule_impact_days: Number(d.schedule_impact_days) || 0,
    owner_id: d.owner_id,
    mitigation: d.mitigation || null,
    contingency: d.contingency || null,
    residual_probability: d.residual_probability,
    residual_impact: d.residual_impact,
    response: d.response,
    review_date: d.review_date || null,
  }) as RiskUpdate

function History({ id }: { id: number }) {
  const { data = [] } = useRiskHistory(id)
  return (
    <ol className='space-y-2 text-sm'>
      {data.map((h, i) => (
        <li key={i} className='flex flex-wrap items-center gap-2'>
          <StatusBadge status={h.to_status} />
          <span className='text-muted-foreground'>
            {h.changed_at ? new Date(h.changed_at).toLocaleString() : ''}
          </span>
          {h.note ? <span>— {h.note}</span> : null}
        </li>
      ))}
    </ol>
  )
}

export function RiskSheet({
  projectId,
  risk,
  open,
  onClose,
  format,
}: {
  projectId: number
  risk?: Risk
  open: boolean
  onClose: () => void
  format: (v: string | number | null | undefined) => string
}) {
  const { t } = useTranslation()
  const session = useSession()
  const editable = can(session, risk ? 'risk.update' : 'risk.create')
  const [draft, setDraft] = useState<Draft>(() => fromRisk(risk))
  const save = useSaveRisk(projectId)
  const move = useRiskStatus(projectId)
  const remove = useDeleteRisk(projectId)
  const { data: people = [] } = usePeople(
    '',
    false,
    can(session, 'people.read')
  )

  const set = <K extends keyof Draft>(key: K, value: Draft[K]) =>
    setDraft((d) => ({ ...d, [key]: value }))
  const opts = (values: readonly string[], prefix?: string) =>
    values.map((v) => ({
      value: v,
      label: prefix ? t(`${prefix}.${v}`) : statusLabel(v),
    }))
  const owners = [
    ...people.map((p) => ({ value: String(p.id), label: p.name })),
    ...(people.some((p) => p.id === session.id)
      ? []
      : [{ value: String(session.id), label: session.name }]),
    ...(risk?.owner_id &&
    risk.owner_name &&
    !people.some((p) => p.id === risk.owner_id) &&
    risk.owner_id !== session.id
      ? [{ value: String(risk.owner_id), label: risk.owner_name }]
      : []),
  ]
  const exposure =
    Math.round(
      Number(draft.probability) * Number(draft.cost_impact || 0) * 100
    ) / 100

  return (
    <RecordSheet
      open={open}
      onClose={onClose}
      wide
      title={risk ? `${risk.code} · ${risk.title}` : t('risk.new')}
      badges={
        risk ? (
          <>
            <StatusBadge status={risk.status} />
            <StatusBadge status={risk.impact} />
            {risk.review_due ? <StatusBadge status='overdue' /> : null}
          </>
        ) : null
      }
      record={
        risk ? { projectId, entityType: 'risk', entityId: risk.id } : undefined
      }
      tabs={
        risk ? { [t('risk.history')]: <History id={risk.id} /> } : undefined
      }
    >
      <form
        className='grid gap-3 sm:grid-cols-2'
        onSubmit={(e) => {
          e.preventDefault()
          save.mutate(
            { id: risk?.id, body: toBody(draft) },
            { onSuccess: () => !risk && onClose() }
          )
        }}
      >
        <Field label={t('risk.title_field')} className='sm:col-span-2'>
          <Input
            value={draft.title}
            onChange={(e) => set('title', e.target.value)}
            required
            disabled={!editable}
          />
        </Field>
        <Field label={t('risk.category')}>
          <SelectField
            value={draft.category}
            onChange={(v) => set('category', v ?? 'technical')}
            options={opts(CATEGORIES, 'risk.cat')}
            disabled={!editable}
          />
        </Field>
        <Field label={t('risk.owner')}>
          <SelectField
            value={draft.owner_id ? String(draft.owner_id) : null}
            onChange={(v) => set('owner_id', v ? Number(v) : null)}
            options={owners}
            allowNone
            disabled={!editable}
          />
        </Field>
        <Field label={t('risk.description_field')} className='sm:col-span-2'>
          <Textarea
            value={draft.description}
            onChange={(e) => set('description', e.target.value)}
            rows={2}
            disabled={!editable}
          />
        </Field>
        <Field label={t('risk.cause')}>
          <Textarea
            value={draft.cause}
            onChange={(e) => set('cause', e.target.value)}
            rows={2}
            disabled={!editable}
          />
        </Field>
        <Field label={t('risk.effect')}>
          <Textarea
            value={draft.effect}
            onChange={(e) => set('effect', e.target.value)}
            rows={2}
            disabled={!editable}
          />
        </Field>
        <Field label={t('risk.probability')}>
          <SelectField
            value={draft.probability}
            onChange={(v) => set('probability', v ?? '0.5')}
            options={PROBABILITIES.map((p) => ({ value: p, label: p }))}
            disabled={!editable}
          />
        </Field>
        <Field label={t('risk.impact')}>
          <SelectField
            value={draft.impact}
            onChange={(v) => set('impact', v ?? 'medium')}
            options={opts(IMPACTS, 'risk.imp')}
            disabled={!editable}
          />
        </Field>
        <Field label={t('risk.cost_impact')}>
          <Input
            type='number'
            min={0}
            step='0.01'
            value={draft.cost_impact}
            onChange={(e) => set('cost_impact', e.target.value)}
            disabled={!editable}
          />
        </Field>
        <Field label={t('risk.schedule_impact')}>
          <Input
            type='number'
            min={0}
            value={draft.schedule_impact_days}
            onChange={(e) => set('schedule_impact_days', e.target.value)}
            disabled={!editable}
          />
        </Field>
        <p className='text-sm text-muted-foreground sm:col-span-2'>
          {t('risk.exposure')}:{' '}
          <span className='font-semibold text-foreground tabular-nums'>
            {format(exposure)}
          </span>
        </p>
        <Field label={t('risk.response')}>
          <SelectField
            value={draft.response}
            onChange={(v) => set('response', v)}
            options={opts(RESPONSES, 'risk.resp')}
            allowNone
            disabled={!editable}
          />
        </Field>
        <Field label={t('risk.review_date')}>
          <Input
            type='date'
            value={draft.review_date}
            onChange={(e) => set('review_date', e.target.value)}
            disabled={!editable}
          />
        </Field>
        <Field label={t('risk.mitigation')} className='sm:col-span-2'>
          <Textarea
            value={draft.mitigation}
            onChange={(e) => set('mitigation', e.target.value)}
            rows={2}
            disabled={!editable}
          />
        </Field>
        <Field label={t('risk.contingency')} className='sm:col-span-2'>
          <Textarea
            value={draft.contingency}
            onChange={(e) => set('contingency', e.target.value)}
            rows={2}
            disabled={!editable}
          />
        </Field>
        <Field label={t('risk.residual_probability')}>
          <SelectField
            value={draft.residual_probability}
            onChange={(v) => set('residual_probability', v)}
            options={PROBABILITIES.map((p) => ({ value: p, label: p }))}
            allowNone
            disabled={!editable}
          />
        </Field>
        <Field label={t('risk.residual_impact')}>
          <SelectField
            value={draft.residual_impact}
            onChange={(v) => set('residual_impact', v)}
            options={opts(IMPACTS, 'risk.imp')}
            allowNone
            disabled={!editable}
          />
        </Field>

        <div className='flex flex-wrap items-center gap-2 pt-2 sm:col-span-2'>
          {editable ? (
            <Button type='submit' size='sm' disabled={save.isPending}>
              {risk ? t('common.save') : t('risk.create')}
            </Button>
          ) : null}
          {risk && can(session, 'risk.transition')
            ? (NEXT_STATUS[risk.status] ?? []).map((s) => (
                <Button
                  key={s}
                  type='button'
                  size='sm'
                  variant='outline'
                  disabled={move.isPending}
                  onClick={() => move.mutate({ id: risk.id, status: s })}
                >
                  {t('risk.move_to', { status: statusLabel(s) })}
                </Button>
              ))
            : null}
          {risk && can(session, 'risk.delete') ? (
            <Button
              type='button'
              size='sm'
              variant='ghost'
              className='ms-auto text-red-600'
              onClick={() =>
                remove.mutate(risk.id, { onSuccess: () => onClose() })
              }
            >
              <Trash2 /> {t('risk.delete')}
            </Button>
          ) : null}
        </div>
      </form>
    </RecordSheet>
  )
}
