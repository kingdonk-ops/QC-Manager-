import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { can, useSession } from '@/lib/session'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { NativeSelect } from '@/components/native-select'
import { Field } from '@/components/records/fields'
import { RecordSheet } from '@/components/records/record-sheet'
import { statusLabel } from '@/components/records/status'
import { StatusBadge } from '@/components/records/status-badge'
import {
  INSPECTION_KINDS,
  NEXT,
  TAGS,
  TAG_CLASSES,
  stepPermission,
  useDecideModification,
  useHistory,
  useInspect,
  useInspections,
  useModifications,
  useRequestInspection,
  useRequestModification,
  useScaffold,
  useTransition,
  useUpdateScaffold,
} from './api'

export function TagPill({ tag, no }: { tag: string; no?: string | null }) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded px-2 py-0.5 text-xs font-semibold uppercase',
        TAG_CLASSES[tag] ?? TAG_CLASSES.none
      )}
    >
      {tag === 'none' ? 'untagged' : tag}
      {no ? <span className='font-mono normal-case'>{no}</span> : null}
    </span>
  )
}

const DEFAULT_CHECKLIST = [
  'Base plates, sole boards and ground conditions',
  'Standards plumb, ledgers and transoms secure',
  'Bracing and ties in place',
  'Platforms fully boarded, no gaps',
  'Guardrails, mid-rails and toe boards',
  'Access ladder or stair secure',
]

function InspectForm({ id, onDone }: { id: number; onDone: () => void }) {
  const { t } = useTranslation()
  const inspect = useInspect(id)
  const [kind, setKind] = useState('periodic')
  const [tag, setTag] = useState('green')
  const [tagNo, setTagNo] = useState('')
  const [restrictions, setRestrictions] = useState('')
  const [checks, setChecks] = useState(DEFAULT_CHECKLIST.map(() => true))
  return (
    <form
      className='grid gap-3 rounded-md border p-3'
      onSubmit={(e) => {
        e.preventDefault()
        inspect.mutate(
          {
            kind: kind as never,
            tag: tag as never,
            tag_no: tagNo || null,
            restrictions: restrictions || null,
            checklist: DEFAULT_CHECKLIST.map((item, i) => ({
              item,
              ok: checks[i],
            })),
          },
          { onSuccess: onDone }
        )
      }}
    >
      <div className='grid grid-cols-3 gap-2'>
        <Field label={t('scaffolds.kind')}>
          <NativeSelect
            values={INSPECTION_KINDS}
            value={kind}
            onChange={(e) => setKind(e.target.value)}
          />
        </Field>
        <Field label={t('scaffolds.tag')}>
          <NativeSelect
            values={TAGS}
            value={tag}
            onChange={(e) => setTag(e.target.value)}
          />
        </Field>
        <Field label={t('scaffolds.tag_no')}>
          <Input value={tagNo} onChange={(e) => setTagNo(e.target.value)} />
        </Field>
      </div>
      <div className='grid gap-1'>
        {DEFAULT_CHECKLIST.map((item, i) => (
          <label key={item} className='flex items-center gap-2 text-sm'>
            <input
              type='checkbox'
              checked={checks[i]}
              onChange={(e) =>
                setChecks(
                  checks.map((c, j) => (j === i ? e.target.checked : c))
                )
              }
            />
            {item}
          </label>
        ))}
      </div>
      {tag === 'yellow' ? (
        <Field label={t('scaffolds.restrictions')}>
          <Textarea
            value={restrictions}
            onChange={(e) => setRestrictions(e.target.value)}
          />
        </Field>
      ) : null}
      <Button type='submit' size='sm' disabled={inspect.isPending}>
        {t('scaffolds.record_inspection')}
      </Button>
    </form>
  )
}

function Inspections({ id }: { id: number }) {
  const { data = [] } = useInspections(id)
  return (
    <ul className='grid gap-2 text-sm'>
      {data.map((i) => (
        <li key={i.id} className='rounded-md border p-2'>
          <div className='flex items-center justify-between gap-2'>
            <TagPill tag={i.tag} no={i.tag_no} />
            <span className='text-xs text-muted-foreground'>
              {statusLabel(i.kind)} ·{' '}
              {new Date(i.inspected_at).toLocaleString()} · {i.inspector_name}
            </span>
          </div>
          {i.restrictions ? <p className='mt-1'>{i.restrictions}</p> : null}
          {i.next_due_at ? (
            <p className='text-xs text-muted-foreground'>
              Next due {new Date(i.next_due_at).toLocaleDateString()}
            </p>
          ) : null}
        </li>
      ))}
    </ul>
  )
}

function Modifications({ id }: { id: number }) {
  const { t } = useTranslation()
  const session = useSession()
  const { data = [] } = useModifications(id)
  const request = useRequestModification(id)
  const decide = useDecideModification(id)
  const [description, setDescription] = useState('')
  return (
    <div className='grid gap-3 text-sm'>
      {data.map((m) => (
        <div key={m.id} className='grid gap-1 rounded-md border p-2'>
          <div className='flex items-center justify-between'>
            <StatusBadge status={m.status} />
            <div className='flex gap-1'>
              {m.status === 'requested' && can(session, 'scaffolds.approve') ? (
                <>
                  <Button
                    size='sm'
                    variant='outline'
                    onClick={() =>
                      decide.mutate({ modId: m.id, status: 'approved' })
                    }
                  >
                    {t('scaffolds.approve')}
                  </Button>
                  <Button
                    size='sm'
                    variant='outline'
                    onClick={() =>
                      decide.mutate({ modId: m.id, status: 'rejected' })
                    }
                  >
                    {t('scaffolds.reject')}
                  </Button>
                </>
              ) : null}
              {m.status === 'approved' &&
              can(session, 'scaffolds.transition') ? (
                <Button
                  size='sm'
                  variant='outline'
                  onClick={() =>
                    decide.mutate({ modId: m.id, status: 'completed' })
                  }
                >
                  {t('scaffolds.complete')}
                </Button>
              ) : null}
            </div>
          </div>
          <p>{m.description}</p>
        </div>
      ))}
      {can(session, 'scaffolds.create') ? (
        <form
          className='grid gap-2'
          onSubmit={(e) => {
            e.preventDefault()
            request.mutate(
              { description },
              { onSuccess: () => setDescription('') }
            )
          }}
        >
          <Textarea
            aria-label={t('scaffolds.modification')}
            placeholder={t('scaffolds.modification_placeholder')}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            required
          />
          <Button size='sm' type='submit' variant='outline'>
            {t('scaffolds.request_modification')}
          </Button>
        </form>
      ) : null}
    </div>
  )
}

function History({ id }: { id: number }) {
  const { data = [] } = useHistory(id)
  return (
    <ol className='grid gap-1 text-sm'>
      {data.map((h, i) => (
        <li key={i} className='flex justify-between gap-2'>
          <span>
            {h.from_status ? `${statusLabel(h.from_status)} → ` : ''}
            {statusLabel(h.to_status)}
            {h.note ? ` · ${h.note}` : ''}
          </span>
          <span className='text-xs text-muted-foreground'>
            {h.changed_at ? new Date(h.changed_at).toLocaleString() : ''}
          </span>
        </li>
      ))}
    </ol>
  )
}

export function ScaffoldSheet({
  id,
  onClose,
}: {
  id: number | null
  onClose: () => void
}) {
  const { t } = useTranslation()
  const session = useSession()
  const { data: s } = useScaffold(id)
  const transition = useTransition(id ?? 0)
  const update = useUpdateScaffold(id ?? 0)
  const requestInspection = useRequestInspection(id ?? 0)
  const [inspecting, setInspecting] = useState(false)
  if (!id || !s) return null
  const steps = (NEXT[s.status] ?? []).filter(
    (target) =>
      can(session, stepPermission(target)) ||
      (target === 'cancelled' && s.requested_by_id === session.id)
  )
  const standing = [
    'erected',
    'in_use',
    'modifying',
    'dismantle_requested',
    'dismantling',
  ].includes(s.status)
  return (
    <RecordSheet
      open
      onClose={onClose}
      wide
      title={`${s.code}${s.tag_no ? ` · ${s.tag_no}` : ''}`}
      subtitle={s.node_path ?? undefined}
      badges={
        <>
          <StatusBadge status={s.status} />
          <TagPill tag={s.effective_tag} />
          {s.inspection_overdue ? <StatusBadge status='overdue' /> : null}
        </>
      }
      record={{
        projectId: s.project_id,
        entityType: 'scaffold',
        entityId: s.id,
      }}
      tabs={{
        Inspections: <Inspections id={s.id} />,
        Modifications: <Modifications id={s.id} />,
        History: <History id={s.id} />,
      }}
    >
      <div className='grid gap-4 text-sm'>
        <div className='flex flex-wrap gap-2'>
          {steps.map((target) => (
            <Button
              key={target}
              size='sm'
              variant={target === 'rejected' ? 'outline' : 'default'}
              disabled={transition.isPending}
              onClick={() => transition.mutate({ status: target })}
            >
              {statusLabel(target)}
            </Button>
          ))}
          {standing && can(session, 'scaffolds.inspect') ? (
            <Button
              size='sm'
              variant='outline'
              onClick={() => setInspecting(!inspecting)}
            >
              {t('scaffolds.inspect')}
            </Button>
          ) : null}
          {standing && can(session, 'scaffolds.create') ? (
            <Button
              size='sm'
              variant='outline'
              onClick={() => requestInspection.mutate({ reason: 'ad_hoc' })}
            >
              {t('scaffolds.request_inspection')}
            </Button>
          ) : null}
        </div>
        {inspecting ? (
          <InspectForm id={s.id} onDone={() => setInspecting(false)} />
        ) : null}
        <dl className='grid grid-cols-2 gap-x-4 gap-y-2'>
          <dt className='text-muted-foreground'>{t('scaffolds.type')}</dt>
          <dd>
            {statusLabel(s.scaffold_type)} · {statusLabel(s.duty_class)}
          </dd>
          <dt className='text-muted-foreground'>{t('scaffolds.purpose')}</dt>
          <dd>{s.purpose ?? '—'}</dd>
          <dt className='text-muted-foreground'>{t('scaffolds.dimensions')}</dt>
          <dd>
            {Object.entries(s.dimensions)
              .map(([k, v]) => `${k.replace(/_m$/, '')} ${v}`)
              .join(' · ') || '—'}
          </dd>
          <dt className='text-muted-foreground'>
            {t('scaffolds.required_by')}
          </dt>
          <dd>{s.required_by ?? '—'}</dd>
          <dt className='text-muted-foreground'>{t('scaffolds.custodian')}</dt>
          <dd>{s.custodian_name ?? '—'}</dd>
          <dt className='text-muted-foreground'>
            {t('scaffolds.last_inspected')}
          </dt>
          <dd>
            {s.last_inspected_at
              ? new Date(s.last_inspected_at).toLocaleString()
              : '—'}
          </dd>
          <dt className='text-muted-foreground'>{t('scaffolds.next_due')}</dt>
          <dd
            className={cn(s.inspection_overdue && 'font-semibold text-red-600')}
          >
            {s.next_inspection_due
              ? new Date(s.next_inspection_due).toLocaleString()
              : '—'}
          </dd>
          <dt className='text-muted-foreground'>{t('scaffolds.erected')}</dt>
          <dd>
            {s.erected_on ?? '—'}
            {s.dismantled_on ? ` → ${s.dismantled_on}` : ''} ({s.days_erected}{' '}
            {t('scaffolds.days')})
          </dd>
          <dt className='text-muted-foreground'>
            {t('scaffolds.restrictions')}
          </dt>
          <dd>{s.tag_restrictions ?? '—'}</dd>
        </dl>
        {can(session, 'scaffolds.update') ? (
          <div className='grid grid-cols-2 gap-3'>
            <Field label={t('scaffolds.interval_days')}>
              <Input
                type='number'
                min={1}
                max={90}
                defaultValue={s.inspection_interval_days}
                onBlur={(e) =>
                  Number(e.target.value) !== s.inspection_interval_days &&
                  update.mutate({
                    inspection_interval_days: Number(e.target.value),
                  })
                }
              />
            </Field>
            <Field label={t('scaffolds.hire_rate')}>
              <Input
                type='number'
                min={0}
                step='0.01'
                defaultValue={s.hire_rate ?? ''}
                onBlur={(e) =>
                  update.mutate({ hire_rate: e.target.value || null })
                }
              />
            </Field>
          </div>
        ) : null}
      </div>
    </RecordSheet>
  )
}
