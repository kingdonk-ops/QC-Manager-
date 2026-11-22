import { useState, type ReactNode } from 'react'
import { Check, FileText, Plus, Trash2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { can, useSession } from '@/lib/session'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { NativeSelect, UserSelect } from '@/components/native-select'
import { RecordSheet } from '@/components/records/record-sheet'
import { statusLabel } from '@/components/records/status'
import { StatusBadge } from '@/components/records/status-badge'
import {
  ACTION_STATUSES,
  DISPOSITIONS,
  LIFECYCLE,
  NEXT,
  type Ncr,
  type NcrUpdate,
  ROOT_CAUSES,
  SEVERITIES,
  SOURCES,
  useAddAction,
  useContactOptions,
  useDeleteAction,
  useNcr,
  useNcrHistory,
  useNcrStatus,
  useUpdateAction,
  useUpdateNcr,
} from './api'

function Field({
  label,
  htmlFor,
  children,
  className,
}: {
  label: string
  htmlFor?: string
  children: ReactNode
  className?: string
}) {
  return (
    <div className={cn('grid gap-1.5', className)}>
      <Label htmlFor={htmlFor}>{label}</Label>
      {children}
    </div>
  )
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className='grid gap-3 border-t pt-3'>
      <h4 className='text-sm font-semibold'>{title}</h4>
      <div className='grid gap-3 sm:grid-cols-2'>{children}</div>
    </section>
  )
}

export function Stepper({ status }: { status: string }) {
  const { t } = useTranslation()
  const at = LIFECYCLE.indexOf(status as (typeof LIFECYCLE)[number])
  return (
    <ol className='flex flex-wrap gap-1' aria-label={t('ncr.lifecycle')}>
      {LIFECYCLE.map((step, i) => (
        <li
          key={step}
          aria-current={i === at ? 'step' : undefined}
          className={cn(
            'flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs',
            i < at && 'border-green-600/40 text-green-700 dark:text-green-400',
            i === at && 'border-primary bg-primary text-primary-foreground',
            i > at && 'text-muted-foreground'
          )}
        >
          {i < at ? <Check className='size-3' /> : null}
          {statusLabel(step)}
        </li>
      ))}
    </ol>
  )
}

const money = (v: string | number | null | undefined) =>
  Number(v ?? 0).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })

function DetailsForm({ ncr, editable }: { ncr: Ncr; editable: boolean }) {
  const { t } = useTranslation()
  const session = useSession()
  const update = useUpdateNcr(ncr.id)
  const { data: contacts = [] } = useContactOptions(
    can(session, 'contacts.read')
  )
  const [draft, setDraft] = useState<Ncr>(ncr)
  const set = (patch: Partial<Ncr>) => setDraft({ ...draft, ...patch })
  const text = (key: keyof Ncr) => ({
    value: (draft[key] as string | null) ?? '',
    disabled: !editable,
    onChange: (
      e: React.ChangeEvent<
        HTMLInputElement & HTMLTextAreaElement & HTMLSelectElement
      >
    ) => set({ [key]: e.target.value } as Partial<Ncr>),
  })
  const fields: (keyof NcrUpdate)[] = [
    'title',
    'description',
    'location',
    'trade',
    'severity',
    'source',
    'source_reference',
    'spec_reference',
    'raised_on',
    'responsible_user_id',
    'responsible_contact_id',
    'root_cause_category',
    'root_cause_description',
    'disposition',
    'disposition_notes',
    'concession_reference',
    'rework_cost',
    'delay_cost',
    'other_cost',
    'days_delay',
  ]
  const total =
    Number(draft.rework_cost || 0) +
    Number(draft.delay_cost || 0) +
    Number(draft.other_cost || 0)

  return (
    <form
      className='grid gap-4'
      onSubmit={(e) => {
        e.preventDefault()
        const changes: Record<string, unknown> = {}
        for (const key of fields) {
          const before = ncr[key as keyof Ncr]
          let after = draft[key as keyof Ncr] as unknown
          if (after === '') after = null
          if (after !== before) changes[key] = after
        }
        if (!Object.keys(changes).length) return
        update.mutate(changes as NcrUpdate, {
          onSuccess: () => toast.success(t('ncr.saved')),
        })
      }}
    >
      <Section title={t('ncr.details')}>
        <Field
          label={t('ncr.title_field')}
          htmlFor='ncr-title'
          className='sm:col-span-2'
        >
          <Input id='ncr-title' required {...text('title')} />
        </Field>
        <Field
          label={t('ncr.description_field')}
          htmlFor='ncr-desc'
          className='sm:col-span-2'
        >
          <Textarea id='ncr-desc' {...text('description')} />
        </Field>
        <Field label={t('ncr.severity')} htmlFor='ncr-sev'>
          <NativeSelect
            id='ncr-sev'
            values={SEVERITIES}
            {...text('severity')}
          />
        </Field>
        <Field label={t('ncr.source')} htmlFor='ncr-src'>
          <NativeSelect id='ncr-src' values={SOURCES} {...text('source')} />
        </Field>
        <Field label={t('ncr.location')} htmlFor='ncr-loc'>
          <Input id='ncr-loc' {...text('location')} />
        </Field>
        <Field label={t('ncr.trade')} htmlFor='ncr-trade'>
          <Input id='ncr-trade' {...text('trade')} />
        </Field>
        <Field label={t('ncr.spec_reference')} htmlFor='ncr-spec'>
          <Input id='ncr-spec' {...text('spec_reference')} />
        </Field>
        <Field label={t('ncr.source_reference')} htmlFor='ncr-srcref'>
          <Input id='ncr-srcref' {...text('source_reference')} />
        </Field>
        <Field label={t('ncr.raised_on')} htmlFor='ncr-raised'>
          <Input id='ncr-raised' type='date' {...text('raised_on')} />
        </Field>
        <Field label={t('ncr.raised_by')}>
          <p className='py-2 text-sm'>{ncr.raised_by_name ?? '—'}</p>
        </Field>
        <Field label={t('ncr.responsible_user')}>
          <UserSelect
            value={draft.responsible_user_id}
            onChange={(id) => set({ responsible_user_id: id })}
          />
        </Field>
        <Field label={t('ncr.responsible_party')} htmlFor='ncr-contact'>
          <NativeSelect
            id='ncr-contact'
            placeholder='—'
            disabled={!editable}
            options={[
              ...contacts.map((c) => ({
                value: String(c.id),
                label: `${c.full_name}${c.company_name ? ` (${c.company_name})` : ''}`,
              })),
              ...(draft.responsible_contact_id &&
              !contacts.some((c) => c.id === draft.responsible_contact_id)
                ? [
                    {
                      value: String(draft.responsible_contact_id),
                      label: ncr.responsible_contact_name ?? '—',
                    },
                  ]
                : []),
            ]}
            value={
              draft.responsible_contact_id
                ? String(draft.responsible_contact_id)
                : ''
            }
            onChange={(e) =>
              set({
                responsible_contact_id: e.target.value
                  ? Number(e.target.value)
                  : null,
              })
            }
          />
        </Field>
      </Section>

      <Section title={t('ncr.root_cause')}>
        <Field label={t('ncr.root_cause_category')} htmlFor='ncr-rc'>
          <NativeSelect
            id='ncr-rc'
            placeholder='—'
            values={ROOT_CAUSES}
            {...text('root_cause_category')}
          />
        </Field>
        <Field
          label={t('ncr.root_cause_description')}
          htmlFor='ncr-rcd'
          className='sm:col-span-2'
        >
          <Textarea id='ncr-rcd' {...text('root_cause_description')} />
        </Field>
      </Section>

      <Section title={t('ncr.disposition')}>
        <Field label={t('ncr.disposition')} htmlFor='ncr-disp'>
          <NativeSelect
            id='ncr-disp'
            placeholder='—'
            values={DISPOSITIONS}
            {...text('disposition')}
          />
        </Field>
        {draft.disposition === 'use_as_is' ? (
          <Field label={t('ncr.concession_reference')} htmlFor='ncr-con'>
            <Input id='ncr-con' {...text('concession_reference')} />
          </Field>
        ) : (
          <span />
        )}
        <Field
          label={t('ncr.disposition_notes')}
          htmlFor='ncr-dn'
          className='sm:col-span-2'
        >
          <Textarea id='ncr-dn' {...text('disposition_notes')} />
        </Field>
      </Section>

      <Section title={t('ncr.cost_impact')}>
        {(['rework_cost', 'delay_cost', 'other_cost'] as const).map((key) => (
          <Field key={key} label={t(`ncr.${key}`)} htmlFor={`ncr-${key}`}>
            <Input
              id={`ncr-${key}`}
              type='number'
              inputMode='decimal'
              min={0}
              step='0.01'
              className='tabular-nums'
              {...text(key)}
            />
          </Field>
        ))}
        <Field label={t('ncr.days_delay')} htmlFor='ncr-days'>
          <Input
            id='ncr-days'
            type='number'
            min={0}
            value={draft.days_delay}
            disabled={!editable}
            onChange={(e) => set({ days_delay: Number(e.target.value) || 0 })}
          />
        </Field>
        <Field label={t('ncr.total_cost')}>
          <p className='py-2 text-lg font-semibold tabular-nums'>
            {money(total)}
          </p>
        </Field>
      </Section>
      {editable ? (
        <Button type='submit' className='w-fit' disabled={update.isPending}>
          {t('ncr.save')}
        </Button>
      ) : null}
    </form>
  )
}

function Transitions({ ncr }: { ncr: Ncr }) {
  const { t } = useTranslation()
  const move = useNcrStatus(ncr.id)
  const [note, setNote] = useState('')
  const next = NEXT[ncr.status] ?? []
  if (!next.length) return null
  return (
    <div className='flex flex-wrap items-center gap-2'>
      <Input
        className='h-8 flex-1'
        placeholder={t('ncr.transition_note')}
        value={note}
        onChange={(e) => setNote(e.target.value)}
      />
      {next.map((target) => (
        <Button
          key={target}
          size='sm'
          variant={
            target === 'corrective_action_planned' && ncr.status === 'verified'
              ? 'outline'
              : 'default'
          }
          disabled={move.isPending}
          onClick={() =>
            move.mutate(
              { status: target, note: note || undefined },
              { onSuccess: () => setNote('') }
            )
          }
        >
          {target === 'corrective_action_planned' && ncr.status === 'verified'
            ? t('ncr.verification_failed')
            : `→ ${statusLabel(target)}`}
        </Button>
      ))}
    </div>
  )
}

function Capa({ ncr, editable }: { ncr: Ncr; editable: boolean }) {
  const { t } = useTranslation()
  const add = useAddAction(ncr.id)
  const update = useUpdateAction(ncr.id)
  const remove = useDeleteAction(ncr.id)
  const blank = {
    description: '',
    kind: 'corrective' as 'corrective' | 'preventive',
    responsible_id: null as number | null,
    due_date: '',
    verification_criteria: '',
  }
  const [draft, setDraft] = useState(blank)

  return (
    <div className='grid gap-3'>
      {ncr.actions.length === 0 ? (
        <p className='text-sm text-muted-foreground'>{t('ncr.no_actions')}</p>
      ) : null}
      {ncr.actions.map((a) => (
        <div key={a.id} className='grid gap-2 rounded-md border p-3 text-sm'>
          <div className='flex items-start gap-2'>
            <StatusBadge status={a.kind} />
            <p className='flex-1'>{a.description}</p>
            {editable ? (
              <button
                aria-label={t('ncr.remove_action')}
                onClick={() => remove.mutate(a.id)}
              >
                <Trash2 className='size-4 text-muted-foreground hover:text-red-600' />
              </button>
            ) : null}
          </div>
          <div className='flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground'>
            <span>
              {t('ncr.responsible')}: {a.responsible_name ?? '—'}
            </span>
            <span className={cn(a.overdue && 'font-medium text-red-600')}>
              {t('ncr.due')}: {a.due_date ?? '—'}
            </span>
            {a.verification_criteria ? (
              <span>
                {t('ncr.verification_criteria')}: {a.verification_criteria}
              </span>
            ) : null}
            {a.verified_at ? (
              <span className='text-green-700 dark:text-green-400'>
                {t('ncr.verified_by', {
                  name: a.verified_by_name ?? '',
                  date: a.verified_at.slice(0, 10),
                })}
              </span>
            ) : null}
          </div>
          <NativeSelect
            className='h-8 w-40'
            aria-label={t('ncr.action_status')}
            disabled={!editable}
            values={ACTION_STATUSES}
            value={a.status}
            onChange={(e) =>
              update.mutate({
                actionId: a.id,
                body: { status: e.target.value as never },
              })
            }
          />
        </div>
      ))}
      {editable ? (
        <form
          className='grid gap-2 rounded-md border border-dashed p-3'
          onSubmit={(e) => {
            e.preventDefault()
            add.mutate(
              {
                description: draft.description,
                kind: draft.kind,
                responsible_id: draft.responsible_id,
                due_date: draft.due_date || null,
                verification_criteria: draft.verification_criteria || null,
              },
              { onSuccess: () => setDraft(blank) }
            )
          }}
        >
          <Textarea
            required
            aria-label={t('ncr.action_description')}
            placeholder={t('ncr.action_description')}
            value={draft.description}
            onChange={(e) =>
              setDraft({ ...draft, description: e.target.value })
            }
          />
          <div className='grid gap-2 sm:grid-cols-3'>
            <NativeSelect
              aria-label={t('ncr.action_kind')}
              values={['corrective', 'preventive']}
              value={draft.kind}
              onChange={(e) =>
                setDraft({
                  ...draft,
                  kind: e.target.value as 'corrective' | 'preventive',
                })
              }
            />
            <UserSelect
              value={draft.responsible_id}
              onChange={(id) => setDraft({ ...draft, responsible_id: id })}
              placeholder={t('ncr.responsible')}
            />
            <Input
              type='date'
              aria-label={t('ncr.due')}
              value={draft.due_date}
              onChange={(e) => setDraft({ ...draft, due_date: e.target.value })}
            />
          </div>
          <Input
            placeholder={t('ncr.verification_criteria')}
            value={draft.verification_criteria}
            onChange={(e) =>
              setDraft({ ...draft, verification_criteria: e.target.value })
            }
          />
          <Button
            size='sm'
            type='submit'
            className='w-fit'
            disabled={add.isPending}
          >
            <Plus /> {t('ncr.add_action')}
          </Button>
        </form>
      ) : null}
    </div>
  )
}

function History({ id }: { id: number }) {
  const { data = [] } = useNcrHistory(id)
  return (
    <ol className='grid gap-2 text-sm'>
      {data.map((h, i) => (
        <li key={i} className='flex flex-wrap items-center gap-2'>
          <span className='text-xs text-muted-foreground tabular-nums'>
            {h.changed_at?.slice(0, 16).replace('T', ' ')}
          </span>
          <StatusBadge status={h.to_status} />
          <span className='text-muted-foreground'>{h.changed_by_name}</span>
          {h.note ? <span>· {h.note}</span> : null}
        </li>
      ))}
    </ol>
  )
}

export function NcrSheet({
  id,
  onClose,
}: {
  id: number | null
  onClose: () => void
}) {
  const { t } = useTranslation()
  const session = useSession()
  const { data: ncr } = useNcr(id)
  const editable = can(session, 'ncr.update')
  return (
    <RecordSheet
      open={Boolean(id)}
      onClose={onClose}
      wide
      title={ncr ? `${ncr.code} · ${ncr.title}` : '…'}
      subtitle={
        ncr ? (
          <span className='flex flex-wrap items-center gap-2'>
            <span>{[ncr.location, ncr.trade].filter(Boolean).join(' · ')}</span>
            <a
              className='inline-flex items-center gap-1 underline'
              href={`/api/v1/ncr/${ncr.id}/report.pdf`}
              target='_blank'
              rel='noreferrer'
            >
              <FileText className='size-3' /> PDF
            </a>
          </span>
        ) : null
      }
      badges={
        ncr ? (
          <>
            <StatusBadge status={ncr.status} />
            <StatusBadge status={ncr.severity} />
          </>
        ) : null
      }
      record={
        ncr
          ? { projectId: ncr.project_id, entityType: 'ncr', entityId: ncr.id }
          : undefined
      }
      tabs={
        ncr
          ? {
              [`${t('ncr.capa')} (${ncr.actions.length})`]: (
                <Capa ncr={ncr} editable={editable} />
              ),
              [t('ncr.history')]: <History id={ncr.id} />,
            }
          : undefined
      }
    >
      {ncr ? (
        <div className='grid gap-4'>
          <Stepper status={ncr.status} />
          {can(session, 'ncr.transition') ? <Transitions ncr={ncr} /> : null}
          <DetailsForm
            key={`${ncr.id}-${ncr.status}-${ncr.created_at}`}
            ncr={ncr}
            editable={editable}
          />
        </div>
      ) : null}
    </RecordSheet>
  )
}
