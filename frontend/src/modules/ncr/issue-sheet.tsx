import { useState, type ReactNode } from 'react'
import {
  ArrowUpCircle,
  Ban,
  Check,
  FileText,
  Plus,
  Send,
  ShieldAlert,
  Trash2,
} from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { can, useSession } from '@/lib/session'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { NativeSelect, UserSelect } from '@/components/native-select'
import { RecordSheet } from '@/components/records/record-sheet'
import { statusLabel } from '@/components/records/status'
import { StatusBadge } from '@/components/records/status-badge'
import {
  ACTION_STATUSES,
  COMPLETION_EFFECTS,
  DISPOSITIONS,
  type Issue,
  type IssueUpdate,
  MDR_EFFECTS,
  PUNCH_CATEGORIES,
  ROOT_CAUSES,
  SEVERITIES,
  VISIBILITIES,
  useAddAction,
  useDeleteAction,
  useFlagLedger,
  useFlagOverride,
  useIssue,
  useIssueHistory,
  useRaiseExternal,
  useRevision,
  useTemplates,
  useTransition,
  useUpdateAction,
  useUpdateIssue,
  useUpgrade,
  useVoid,
} from './api'
import { type Answers, TemplateFields } from './template-fields'
import {
  type FieldDef,
  LIFECYCLES,
  type Move,
  STEPS,
  asType,
  fieldEditable,
  fieldsByStep,
  isOpen,
  lifecycleIndex,
  missingFor,
  movesFor,
  stepAt,
} from './workflow'

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
      {children}
    </section>
  )
}

export function Stepper({ issue }: { issue: Issue }) {
  const { t } = useTranslation()
  const type = asType(issue.issue_type)
  const steps = LIFECYCLES[type]
  const at = lifecycleIndex(type, issue.status)
  return (
    <ol className='flex flex-wrap gap-1' aria-label={t('issues.workflow')}>
      {steps.map((step, i) => (
        <li
          key={step}
          aria-current={i === at ? 'step' : undefined}
          className={cn(
            'flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs',
            at >= 0 &&
              i < at &&
              'border-green-600/40 text-green-700 dark:text-green-400',
            i === at && 'border-primary bg-primary text-primary-foreground',
            (at < 0 || i > at) && 'text-muted-foreground'
          )}
        >
          {at >= 0 && i < at ? <Check className='size-3' /> : null}
          {t(`issues.status.${type}.${step}`, statusLabel(step))}
        </li>
      ))}
      {at < 0 ? <StatusBadge status={issue.status} /> : null}
    </ol>
  )
}

function AttestDialog({
  issue,
  onClose,
  onConfirm,
  pending,
}: {
  issue: Issue
  onClose: () => void
  onConfirm: () => void
  pending: boolean
}) {
  const { t } = useTranslation()
  const [agreed, setAgreed] = useState(false)
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('issues.attest_title')}</DialogTitle>
          <DialogDescription>
            {t('issues.attest_statement', { code: issue.code })}
          </DialogDescription>
        </DialogHeader>
        <label className='flex items-start gap-2 text-sm'>
          <Checkbox
            checked={agreed}
            onCheckedChange={(v) => setAgreed(v === true)}
          />
          {t('issues.attest_confirm')}
        </label>
        <DialogFooter>
          <Button disabled={!agreed || pending} onClick={onConfirm}>
            {t('issues.do.verify_effective')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function Moves({ issue, fields }: { issue: Issue; fields: FieldDef[] }) {
  const { t } = useTranslation()
  const session = useSession()
  const move = useTransition(issue.id)
  const [note, setNote] = useState('')
  const [attesting, setAttesting] = useState<Move | null>(null)
  const type = asType(issue.issue_type)
  const moves = movesFor(type, issue.status).filter((m) =>
    can(session, m.permission)
  )
  if (!moves.length) return null
  const run = (m: Move) =>
    move.mutate(
      { to: m.to, note: note || undefined, attest: m.attest || undefined },
      {
        onSuccess: () => {
          setNote('')
          setAttesting(null)
        },
      }
    )
  const separationNote =
    type === 'punch' && issue.status !== 'open'
      ? t('issues.rectifier_cannot_verify')
      : type === 'ncr' && issue.status === 'effectiveness'
        ? t('issues.resolver_cannot_verify')
        : null
  return (
    <div className='grid gap-2 rounded-md border bg-muted/30 p-3'>
      <div className='flex flex-wrap items-center gap-2'>
        <Input
          className='h-8 min-w-48 flex-1'
          placeholder={t('issues.transition_note')}
          value={note}
          onChange={(e) => setNote(e.target.value)}
        />
        {moves.map((m) => {
          const missing = m.back
            ? []
            : missingFor(type, issue.status, m.to, fields, issue.answers)
          return (
            <Button
              key={m.to}
              size='sm'
              variant={m.back ? 'outline' : 'default'}
              disabled={move.isPending || (m.needsNote && !note)}
              title={
                missing.length
                  ? `${t('issues.fill_first')}: ${missing.join(', ')}`
                  : undefined
              }
              onClick={() => (m.attest ? setAttesting(m) : run(m))}
            >
              {t(m.label)}
            </Button>
          )
        })}
      </div>
      {separationNote ? (
        <p className='text-xs text-muted-foreground'>{separationNote}</p>
      ) : null}
      {attesting ? (
        <AttestDialog
          issue={issue}
          pending={move.isPending}
          onClose={() => setAttesting(null)}
          onConfirm={() => run(attesting)}
        />
      ) : null}
    </div>
  )
}

const DISPOSITION_STEP = STEPS.ncr.indexOf('disposition')
const ROOT_CAUSE_STEP = STEPS.ncr.indexOf('root_cause')

function DetailsForm({
  issue,
  fields,
  editable,
}: {
  issue: Issue
  fields: FieldDef[]
  editable: boolean
}) {
  const { t } = useTranslation()
  const update = useUpdateIssue(issue.id)
  const [draft, setDraft] = useState<Issue>(issue)
  const [answers, setAnswers] = useState<Answers>(issue.answers)
  const type = asType(issue.issue_type)
  const open = isOpen(issue.status)
  const at = stepAt(type, issue.status)
  const set = (patch: Partial<Issue>) => setDraft({ ...draft, ...patch })
  const text = (key: keyof Issue, enabled = editable) => ({
    value: (draft[key] as string | null) ?? '',
    disabled: !enabled,
    onChange: (
      e: React.ChangeEvent<
        HTMLInputElement & HTMLTextAreaElement & HTMLSelectElement
      >
    ) => set({ [key]: e.target.value } as Partial<Issue>),
  })
  const keysToSave: (keyof IssueUpdate)[] = [
    'title',
    'description',
    'location',
    'trade',
    'spec_reference',
    'due_date',
    'responsible_user_id',
    ...(type === 'punch'
      ? (['punch_category'] as const)
      : ([
          'severity',
          'disposition',
          'disposition_notes',
          'concession_reference',
          'root_cause_category',
          'root_cause_description',
          'rework_cost',
          'delay_cost',
          'other_cost',
          'days_delay',
        ] as const)),
  ]
  const dispositionOpen = editable && open && at <= DISPOSITION_STEP
  const rootCauseOpen = editable && open && at <= ROOT_CAUSE_STEP

  return (
    <form
      className='grid gap-4'
      onSubmit={(e) => {
        e.preventDefault()
        const changes: Record<string, unknown> = {}
        for (const key of keysToSave) {
          const before = issue[key as keyof Issue]
          let after = draft[key as keyof Issue] as unknown
          if (after === '') after = null
          if (after !== before) changes[key] = after
        }
        const changedAnswers = Object.fromEntries(
          Object.entries(answers).filter(
            ([k, v]) =>
              JSON.stringify(v) !== JSON.stringify(issue.answers[k] ?? null)
          )
        )
        if (Object.keys(changedAnswers).length) changes.answers = changedAnswers
        if (!Object.keys(changes).length) return
        update.mutate(changes as IssueUpdate, {
          onSuccess: () => toast.success(t('issues.saved')),
        })
      }}
    >
      <div className='grid gap-3 sm:grid-cols-2'>
        <Field
          label={t('issues.title_field')}
          htmlFor='issue-title'
          className='sm:col-span-2'
        >
          <Input id='issue-title' required {...text('title')} />
        </Field>
        <Field
          label={t('issues.description')}
          htmlFor='issue-desc'
          className='sm:col-span-2'
        >
          <Textarea id='issue-desc' {...text('description')} />
        </Field>
        {type === 'punch' ? (
          <Field label={t('issues.punch_category')} htmlFor='issue-cat'>
            <NativeSelect
              id='issue-cat'
              options={PUNCH_CATEGORIES.map((c) => ({
                value: c,
                label: t(`issues.cat.${c}`),
              }))}
              {...text('punch_category', editable && open)}
            />
          </Field>
        ) : (
          <Field label={t('issues.severity')} htmlFor='issue-sev'>
            <NativeSelect
              id='issue-sev'
              values={SEVERITIES}
              {...text('severity')}
            />
          </Field>
        )}
        <Field label={t('issues.due')} htmlFor='issue-due'>
          <Input id='issue-due' type='date' {...text('due_date')} />
        </Field>
        <Field label={t('issues.responsible')}>
          <UserSelect
            value={draft.responsible_user_id}
            onChange={(id) => set({ responsible_user_id: id })}
          />
        </Field>
        <Field label={t('issues.location')} htmlFor='issue-loc'>
          <Input id='issue-loc' {...text('location')} />
        </Field>
        <Field label={t('issues.trade')} htmlFor='issue-trade'>
          <Input id='issue-trade' {...text('trade')} />
        </Field>
        <Field label={t('issues.spec_reference')} htmlFor='issue-spec'>
          <Input id='issue-spec' {...text('spec_reference')} />
        </Field>
      </div>

      {fieldsByStep(type, fields).map((group) => (
        <Section
          key={group.step}
          title={t(`issues.step.${group.step}`, statusLabel(group.step))}
        >
          <TemplateFields
            fields={group.fields}
            values={answers}
            onChange={(key, value) => setAnswers({ ...answers, [key]: value })}
            editable={(f) => editable && fieldEditable(type, issue.status, f)}
            projectId={issue.project_id}
            entity={{ type: 'ncr', id: issue.id }}
          />
        </Section>
      ))}

      {type === 'ncr' ? (
        <>
          <Section title={t('issues.step.disposition')}>
            <div className='grid gap-3 sm:grid-cols-2'>
              <Field label={t('issues.disposition')} htmlFor='issue-disp'>
                <NativeSelect
                  id='issue-disp'
                  placeholder='—'
                  values={DISPOSITIONS}
                  {...text('disposition', dispositionOpen)}
                />
              </Field>
              <Field label={t('issues.concession')} htmlFor='issue-con'>
                <Input
                  id='issue-con'
                  {...text('concession_reference', dispositionOpen)}
                />
              </Field>
              <Field
                label={t('issues.disposition_notes')}
                htmlFor='issue-dn'
                className='sm:col-span-2'
              >
                <Textarea
                  id='issue-dn'
                  {...text('disposition_notes', dispositionOpen)}
                />
              </Field>
            </div>
          </Section>
          <Section title={t('issues.step.root_cause')}>
            <div className='grid gap-3 sm:grid-cols-2'>
              <Field label={t('issues.root_cause_category')} htmlFor='issue-rc'>
                <NativeSelect
                  id='issue-rc'
                  placeholder='—'
                  values={ROOT_CAUSES}
                  {...text('root_cause_category', rootCauseOpen)}
                />
              </Field>
              <Field
                label={t('issues.root_cause_statement')}
                htmlFor='issue-rcd'
                className='sm:col-span-2'
              >
                <Textarea
                  id='issue-rcd'
                  {...text('root_cause_description', rootCauseOpen)}
                />
              </Field>
            </div>
          </Section>
          <Section title={t('issues.cost_impact')}>
            <div className='grid gap-3 sm:grid-cols-4'>
              {(['rework_cost', 'delay_cost', 'other_cost'] as const).map(
                (key) => (
                  <Field
                    key={key}
                    label={t(`issues.${key}`)}
                    htmlFor={`issue-${key}`}
                  >
                    <Input
                      id={`issue-${key}`}
                      type='number'
                      inputMode='decimal'
                      min={0}
                      step='0.01'
                      {...text(key)}
                    />
                  </Field>
                )
              )}
              <Field label={t('issues.days_delay')} htmlFor='issue-days'>
                <Input
                  id='issue-days'
                  type='number'
                  min={0}
                  value={draft.days_delay}
                  disabled={!editable}
                  onChange={(e) =>
                    set({ days_delay: Number(e.target.value) || 0 })
                  }
                />
              </Field>
            </div>
          </Section>
          {issue.effectiveness_statement ? (
            <Section title={t('issues.step.effectiveness')}>
              <p className='text-sm'>{issue.effectiveness_statement}</p>
              <p className='text-xs text-muted-foreground'>
                {issue.verified_by_name} · {issue.verified_at?.slice(0, 16)}
              </p>
            </Section>
          ) : null}
        </>
      ) : null}
      {editable && issue.status !== 'void' ? (
        <Button type='submit' className='w-fit' disabled={update.isPending}>
          {t('issues.save')}
        </Button>
      ) : null}
    </form>
  )
}

function Capa({ issue, editable }: { issue: Issue; editable: boolean }) {
  const { t } = useTranslation()
  const add = useAddAction(issue.id)
  const update = useUpdateAction(issue.id)
  const remove = useDeleteAction(issue.id)
  const blank = {
    description: '',
    kind: 'corrective' as 'corrective' | 'preventive',
    responsible_id: null as number | null,
    due_date: '',
  }
  const [draft, setDraft] = useState(blank)
  return (
    <div className='grid gap-3'>
      {issue.actions.length === 0 ? (
        <p className='text-sm text-muted-foreground'>
          {t('issues.no_actions')}
        </p>
      ) : null}
      {issue.actions.map((a) => (
        <div key={a.id} className='grid gap-2 rounded-md border p-3 text-sm'>
          <div className='flex items-start gap-2'>
            <StatusBadge status={a.kind} />
            <p className='flex-1'>{a.description}</p>
            {editable ? (
              <button
                aria-label={t('issues.remove_action')}
                onClick={() => remove.mutate(a.id)}
              >
                <Trash2 className='size-4 text-muted-foreground hover:text-red-600' />
              </button>
            ) : null}
          </div>
          <div className='flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground'>
            <span>
              {t('issues.responsible')}: {a.responsible_name ?? '—'}
            </span>
            <span className={cn(a.overdue && 'font-medium text-red-600')}>
              {t('issues.due')}: {a.due_date ?? '—'}
            </span>
            {a.cancel_reason ? <span>· {a.cancel_reason}</span> : null}
          </div>
          <NativeSelect
            className='h-8 w-40'
            aria-label={t('issues.action_status')}
            disabled={!editable}
            values={ACTION_STATUSES}
            value={a.status}
            onChange={(e) => {
              const status = e.target.value
              const cancel_reason =
                status === 'cancelled'
                  ? window.prompt(t('issues.cancel_reason')) || undefined
                  : undefined
              if (status === 'cancelled' && !cancel_reason) return
              update.mutate({
                actionId: a.id,
                body: { status: status as never, cancel_reason },
              })
            }}
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
              },
              { onSuccess: () => setDraft(blank) }
            )
          }}
        >
          <Textarea
            required
            aria-label={t('issues.action_description')}
            placeholder={t('issues.action_description')}
            value={draft.description}
            onChange={(e) =>
              setDraft({ ...draft, description: e.target.value })
            }
          />
          <div className='grid gap-2 sm:grid-cols-3'>
            <NativeSelect
              aria-label={t('issues.action_kind')}
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
              placeholder={t('issues.responsible')}
            />
            <Input
              type='date'
              aria-label={t('issues.due')}
              value={draft.due_date}
              onChange={(e) => setDraft({ ...draft, due_date: e.target.value })}
            />
          </div>
          <Button
            size='sm'
            type='submit'
            className='w-fit'
            disabled={add.isPending}
          >
            <Plus /> {t('issues.add_action')}
          </Button>
        </form>
      ) : null}
    </div>
  )
}

const FLAG_VALUES: Record<string, readonly string[]> = {
  visibility: VISIBILITIES,
  mdr_effect: MDR_EFFECTS,
  completion_effect: COMPLETION_EFFECTS,
}

function OverrideDialog({
  issue,
  flag,
  onClose,
}: {
  issue: Issue
  flag: string
  onClose: () => void
}) {
  const { t } = useTranslation()
  const override = useFlagOverride(issue.id)
  const current = issue[flag as keyof Issue] as string
  const [value, setValue] = useState(
    FLAG_VALUES[flag].find((v) => v !== current) ?? current
  )
  const [reason, setReason] = useState('')
  const locked = issue.origin === 'client' || issue.origin === 'external_audit'
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {t('issues.override_title', { flag: t(`issues.flag.${flag}`) })}
          </DialogTitle>
          <DialogDescription>{t('issues.override_help')}</DialogDescription>
        </DialogHeader>
        <div className='grid gap-3'>
          <Field label={t('issues.new_value')} htmlFor='override-value'>
            <NativeSelect
              id='override-value'
              options={FLAG_VALUES[flag]
                .filter((v) => v !== current)
                .map((v) => ({ value: v, label: statusLabel(v) }))}
              value={value}
              onChange={(e) => setValue(e.target.value)}
            />
          </Field>
          {locked ? (
            <p className='text-xs text-amber-700 dark:text-amber-400'>
              {t('issues.locked_origin')}
            </p>
          ) : null}
          <Field label={t('issues.reason')} htmlFor='override-reason'>
            <Textarea
              id='override-reason'
              required
              value={reason}
              onChange={(e) => setReason(e.target.value)}
            />
          </Field>
        </div>
        <DialogFooter>
          <Button
            disabled={reason.trim().length < 3 || override.isPending}
            onClick={() =>
              override.mutate(
                { flag, value, reason },
                {
                  onSuccess: () => {
                    toast.success(t('issues.override_done'))
                    onClose()
                  },
                }
              )
            }
          >
            {t('issues.override')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function FlagsPanel({ issue }: { issue: Issue }) {
  const { t } = useTranslation()
  const session = useSession()
  const { data: ledger = [] } = useFlagLedger(issue.id)
  const [editing, setEditing] = useState<string | null>(null)
  const manage = can(session, 'ncr.manage') && issue.status !== 'void'
  const flags = ['visibility', 'mdr_effect', 'completion_effect'] as const
  return (
    <div className='grid gap-4'>
      <div className='grid gap-2'>
        {flags.map((flag) => (
          <div
            key={flag}
            className='flex items-center gap-3 rounded-md border px-3 py-2 text-sm'
          >
            <span className='w-40 text-muted-foreground'>
              {t(`issues.flag.${flag}`)}
            </span>
            <StatusBadge status={issue[flag]} />
            {flag === 'completion_effect' && issue.issue_type === 'punch' ? (
              <span className='text-xs text-muted-foreground'>
                {t('issues.punch_completion')}
              </span>
            ) : null}
            {manage ? (
              <Button
                size='sm'
                variant='ghost'
                className='ms-auto'
                onClick={() => setEditing(flag)}
              >
                {t('issues.override')}
              </Button>
            ) : null}
          </div>
        ))}
        <p className='text-xs text-muted-foreground'>
          {t('issues.origin')}: {statusLabel(issue.origin)}
          {issue.client_seen_at
            ? ` · ${t('issues.client_seen', { at: issue.client_seen_at.slice(0, 10) })}`
            : ''}
        </p>
      </div>
      <div className='grid gap-2'>
        <h4 className='text-sm font-semibold'>{t('issues.override_ledger')}</h4>
        {ledger.length === 0 ? (
          <p className='text-sm text-muted-foreground'>
            {t('issues.no_overrides')}
          </p>
        ) : null}
        {ledger.map((e) => (
          <div key={e.id} className='rounded-md border p-2 text-sm'>
            <div className='flex flex-wrap items-center gap-2'>
              <span className='font-medium'>{t(`issues.flag.${e.flag}`)}</span>
              <span>
                {statusLabel(e.old_value)} → {statusLabel(e.new_value)}
              </span>
              {e.loosening ? (
                <span className='rounded bg-amber-500/15 px-1.5 text-xs text-amber-700 dark:text-amber-400'>
                  {t('issues.loosening')}
                </span>
              ) : null}
              <span className='ms-auto text-xs text-muted-foreground'>
                {e.actor_name} · {e.created_at?.slice(0, 16).replace('T', ' ')}
              </span>
            </div>
            <p className='text-muted-foreground'>{e.reason}</p>
          </div>
        ))}
      </div>
      {editing ? (
        <OverrideDialog
          issue={issue}
          flag={editing}
          onClose={() => setEditing(null)}
        />
      ) : null}
    </div>
  )
}

function photosOf(answers: Answers, fields: FieldDef[]) {
  return fields
    .filter((f) => f.type === 'photo')
    .flatMap((f) => (answers[f.key] as number[] | undefined) ?? [])
}

function RaiseExternalDialog({
  issue,
  fields,
  onClose,
  onRaised,
}: {
  issue: Issue
  fields: FieldDef[]
  onClose: () => void
  onRaised: (id: number) => void
}) {
  const { t } = useTranslation()
  const raise = useRaiseExternal(issue.id)
  const { data: templates = [] } = useTemplates(
    issue.project_id,
    'ncr',
    undefined
  )
  const answered = fields.filter(
    (f) => f.type !== 'photo' && issue.answers[f.key] != null
  )
  const photos = photosOf(issue.answers, fields)
  const [templateId, setTemplateId] = useState('')
  const [carryDescription, setCarryDescription] = useState(true)
  const [keys, setKeys] = useState<string[]>(answered.map((f) => f.key))
  const [picked, setPicked] = useState<number[]>(photos)
  const toggle = <T,>(list: T[], v: T) =>
    list.includes(v) ? list.filter((x) => x !== v) : [...list, v]
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className='sm:max-w-lg'>
        <DialogHeader>
          <DialogTitle>{t('issues.raise_external')}</DialogTitle>
          <DialogDescription>
            {t('issues.raise_external_help')}
          </DialogDescription>
        </DialogHeader>
        <div className='grid gap-3 text-sm'>
          <Field label={t('issues.template')} htmlFor='ext-template'>
            <NativeSelect
              id='ext-template'
              placeholder={t('issues.category_default')}
              options={templates
                .filter((tp) => tp.published)
                .map((tp) => ({ value: String(tp.id), label: tp.name }))}
              value={templateId}
              onChange={(e) => setTemplateId(e.target.value)}
            />
          </Field>
          <label className='flex items-center gap-2'>
            <Checkbox
              checked={carryDescription}
              onCheckedChange={(v) => setCarryDescription(v === true)}
            />
            {t('issues.description')}
          </label>
          {answered.map((f) => (
            <label key={f.key} className='flex items-center gap-2'>
              <Checkbox
                checked={keys.includes(f.key)}
                onCheckedChange={() => setKeys(toggle(keys, f.key))}
              />
              {f.label}: {String(issue.answers[f.key])}
            </label>
          ))}
          {photos.length ? (
            <div className='flex flex-wrap gap-2'>
              {photos.map((id) => (
                <label key={id} className='flex items-center gap-1'>
                  <Checkbox
                    checked={picked.includes(id)}
                    onCheckedChange={() => setPicked(toggle(picked, id))}
                  />
                  <img
                    src={`/api/v1/files/${id}/download?inline=true`}
                    alt=''
                    className='size-12 rounded object-cover'
                  />
                </label>
              ))}
            </div>
          ) : null}
          <p className='text-xs text-muted-foreground'>
            {t('issues.never_carried')}
          </p>
        </div>
        <DialogFooter>
          <Button
            disabled={raise.isPending}
            onClick={() =>
              raise.mutate(
                {
                  template_id: templateId ? Number(templateId) : undefined,
                  carry_description: carryDescription,
                  carry_answers: [
                    ...keys,
                    ...fields
                      .filter((f) => f.type === 'photo')
                      .map((f) => f.key),
                  ],
                  carry_photos: picked,
                },
                {
                  onSuccess: (made) => {
                    onClose()
                    onRaised(made.id)
                  },
                }
              )
            }
          >
            <Send /> {t('issues.raise_external')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function ReasonDialog({
  title,
  action,
  pending,
  onClose,
  onConfirm,
}: {
  title: string
  action: string
  pending: boolean
  onClose: () => void
  onConfirm: (reason: string) => void
}) {
  const { t } = useTranslation()
  const [reason, setReason] = useState('')
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
        </DialogHeader>
        <Field label={t('issues.reason')} htmlFor='reason-text'>
          <Textarea
            id='reason-text'
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          />
        </Field>
        <DialogFooter>
          <Button
            disabled={reason.trim().length < 3 || pending}
            onClick={() => onConfirm(reason)}
          >
            {action}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function Escalations({
  issue,
  fields,
  onOpen,
}: {
  issue: Issue
  fields: FieldDef[]
  onOpen: (id: number) => void
}) {
  const { t } = useTranslation()
  const session = useSession()
  const upgrade = useUpgrade(issue.id)
  const voiding = useVoid(issue.id)
  const [dialog, setDialog] = useState<'upgrade' | 'external' | 'void' | null>(
    null
  )
  if (!can(session, 'ncr.manage') || !isOpen(issue.status)) return null
  return (
    <div className='flex flex-wrap gap-2'>
      {issue.issue_type === 'punch' ? (
        <Button
          size='sm'
          variant='outline'
          onClick={() => setDialog('upgrade')}
        >
          <ArrowUpCircle /> {t('issues.upgrade')}
        </Button>
      ) : null}
      {issue.visibility === 'internal' ? (
        <Button
          size='sm'
          variant='outline'
          onClick={() => setDialog('external')}
        >
          <ShieldAlert /> {t('issues.raise_external')}
        </Button>
      ) : null}
      <Button size='sm' variant='ghost' onClick={() => setDialog('void')}>
        <Ban /> {t('issues.void')}
      </Button>
      {dialog === 'upgrade' ? (
        <ReasonDialog
          title={t('issues.upgrade_title', { code: issue.code })}
          action={t('issues.upgrade')}
          pending={upgrade.isPending}
          onClose={() => setDialog(null)}
          onConfirm={(note) =>
            upgrade.mutate(
              { note },
              {
                onSuccess: (made) => {
                  setDialog(null)
                  onOpen(made.id)
                },
              }
            )
          }
        />
      ) : null}
      {dialog === 'void' ? (
        <ReasonDialog
          title={t('issues.void_title', { code: issue.code })}
          action={t('issues.void')}
          pending={voiding.isPending}
          onClose={() => setDialog(null)}
          onConfirm={(reason) =>
            voiding.mutate(reason, { onSuccess: () => setDialog(null) })
          }
        />
      ) : null}
      {dialog === 'external' ? (
        <RaiseExternalDialog
          issue={issue}
          fields={fields}
          onClose={() => setDialog(null)}
          onRaised={onOpen}
        />
      ) : null}
    </div>
  )
}

function History({ id }: { id: number }) {
  const { data = [] } = useIssueHistory(id)
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

function Links({
  issue,
  onOpen,
}: {
  issue: Issue
  onOpen: (id: number) => void
}) {
  const { t } = useTranslation()
  const links: [string, number | null | undefined][] = [
    ['issues.upgraded_from', issue.upgraded_from_id],
    ['issues.escalated_from', issue.escalated_from_id],
    ['issues.successor', issue.successor_id],
  ]
  const shown = links.filter(([, id]) => id)
  if (!shown.length) return null
  return (
    <div className='flex flex-wrap gap-3 text-sm'>
      {shown.map(([label, id]) => (
        <button
          key={label}
          className='underline'
          onClick={() => id && onOpen(id)}
        >
          {t(label)} #{id}
        </button>
      ))}
    </div>
  )
}

export function IssueSheet({
  id,
  onClose,
  onOpen,
}: {
  id: number | null
  onClose: () => void
  onOpen: (id: number) => void
}) {
  const { t } = useTranslation()
  const session = useSession()
  const { data: issue } = useIssue(id)
  const { data: revision } = useRevision(issue?.template_revision_id)
  const fields = revision?.fields ?? []
  const editable = can(session, 'ncr.update')
  const type = asType(issue?.issue_type)
  return (
    <RecordSheet
      open={Boolean(id)}
      onClose={onClose}
      wide
      title={issue ? `${issue.code} · ${issue.title}` : '…'}
      subtitle={
        issue ? (
          <span className='flex flex-wrap items-center gap-2'>
            <span>
              {issue.template_name}
              {issue.anchor_label
                ? ` · ${issue.anchor_label}`
                : ` · ${t('issues.project_level')}${issue.location_label ? ` (${issue.location_label})` : ''}`}
            </span>
            <a
              className='inline-flex items-center gap-1 underline'
              href={`/api/v1/ncr/${issue.id}/report.pdf`}
              target='_blank'
              rel='noreferrer'
            >
              <FileText className='size-3' /> PDF
            </a>
          </span>
        ) : null
      }
      badges={
        issue ? (
          <>
            <StatusBadge status={issue.status} />
            {type === 'punch' ? (
              <StatusBadge
                status={`cat_${issue.punch_category}`}
                className={
                  issue.punch_category === 'A'
                    ? 'bg-red-500/15 text-red-700 dark:text-red-400'
                    : undefined
                }
              />
            ) : (
              <StatusBadge status={issue.severity} />
            )}
            <StatusBadge status={issue.visibility} />
            {issue.mdr_effect === 'blocks' ? (
              <StatusBadge status='blocks_mdr' />
            ) : null}
          </>
        ) : null
      }
      record={
        issue
          ? {
              projectId: issue.project_id,
              entityType: 'ncr',
              entityId: issue.id,
            }
          : undefined
      }
      tabs={
        issue
          ? {
              ...(type === 'ncr'
                ? {
                    [`${t('issues.capa')} (${issue.actions.length})`]: (
                      <Capa
                        issue={issue}
                        editable={editable && isOpen(issue.status)}
                      />
                    ),
                  }
                : {}),
              [t('issues.flags')]: <FlagsPanel issue={issue} />,
              [t('issues.history')]: <History id={issue.id} />,
            }
          : undefined
      }
    >
      {issue ? (
        <div className='grid gap-4'>
          <Stepper issue={issue} />
          {issue.void_reason ? (
            <p className='text-sm text-red-600'>
              {t('issues.voided')}: {issue.void_reason}
            </p>
          ) : null}
          <Links issue={issue} onOpen={onOpen} />
          <Moves issue={issue} fields={fields} />
          <Escalations issue={issue} fields={fields} onOpen={onOpen} />
          <DetailsForm
            key={`${issue.id}-${issue.status}-${issue.template_revision_id}-${revision ? 'r' : ''}`}
            issue={issue}
            fields={fields}
            editable={editable}
          />
        </div>
      ) : null}
    </RecordSheet>
  )
}
