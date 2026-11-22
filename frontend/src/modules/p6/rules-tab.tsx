import { useState } from 'react'
import { FlaskConical, Plus, Trash2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import { Field, SelectField } from '@/components/records/fields'
import {
  type P6Rule,
  type RuleTestResult,
  useP6Settings,
  useRuleActions,
  useRules,
} from './api'
import { parseSamples } from './helpers'

const KINDS = ['grammar', 'eligibility', 'alias'] as const
const SOURCES = ['name', 'code', 'wbs'] as const
const FIELDS = [
  'task_type',
  'activity_type',
  'name',
  'code',
  'wbs',
  'status_code',
]
const OPS = ['in', 'equals', 'contains', 'matches']

function describe(rule: P6Rule): string {
  const p = rule.params as Record<string, unknown>
  if (rule.kind === 'eligibility')
    return `${String(p.field)} ${String(p.op)} ${((p.values as string[]) ?? []).join(', ')}`
  if (rule.kind === 'alias') return `${rule.pattern} → ${String(p.to)}`
  return `${rule.source}: ${rule.pattern}`
}

function NewRule({ projectId }: { projectId: number }) {
  const { t } = useTranslation()
  const { create } = useRuleActions(projectId)
  const [kind, setKind] = useState<(typeof KINDS)[number]>('grammar')
  const [draft, setDraft] = useState({
    name: '',
    pattern: '',
    source: 'name',
    field: 'activity_type',
    op: 'in',
    values: '',
    to: '',
  })
  const set = (k: keyof typeof draft, v: string) =>
    setDraft((d) => ({ ...d, [k]: v }))
  return (
    <form
      className='grid gap-2 rounded-lg border p-3 sm:grid-cols-6 sm:items-end'
      onSubmit={(e) => {
        e.preventDefault()
        const params =
          kind === 'eligibility'
            ? {
                field: draft.field,
                op: draft.op,
                values: draft.values
                  .split(',')
                  .map((v) => v.trim())
                  .filter(Boolean),
              }
            : kind === 'alias'
              ? { to: draft.to }
              : {}
        create.mutate(
          {
            kind,
            name: draft.name,
            pattern: kind === 'eligibility' ? '' : draft.pattern,
            source: draft.source as 'name',
            params,
            sort_order: 100,
            enabled: true,
          },
          {
            onSuccess: () =>
              setDraft((d) => ({ ...d, name: '', pattern: '', values: '' })),
          }
        )
      }}
    >
      <Field label={t('p6.kind')}>
        <SelectField
          value={kind}
          onChange={(v) => setKind((v as typeof kind) ?? 'grammar')}
          options={KINDS.map((k) => ({ value: k, label: t(`p6.kind.${k}`) }))}
        />
      </Field>
      <Field label={t('p6.rule_name')}>
        <Input
          className='h-8'
          value={draft.name}
          onChange={(e) => set('name', e.target.value)}
          required
        />
      </Field>
      {kind === 'eligibility' ? (
        <>
          <Field label={t('p6.field')}>
            <SelectField
              value={draft.field}
              onChange={(v) => set('field', v ?? 'name')}
              options={FIELDS.map((f) => ({ value: f, label: f }))}
            />
          </Field>
          <Field label={t('p6.op')}>
            <SelectField
              value={draft.op}
              onChange={(v) => set('op', v ?? 'in')}
              options={OPS.map((o) => ({ value: o, label: o }))}
            />
          </Field>
          <Field label={t('p6.values')}>
            <Input
              className='h-8'
              value={draft.values}
              onChange={(e) => set('values', e.target.value)}
              placeholder='Prov Sums, Custom'
              required
            />
          </Field>
        </>
      ) : (
        <>
          <Field
            label={kind === 'alias' ? t('p6.found') : t('p6.pattern')}
            className='sm:col-span-2'
          >
            <Input
              className='h-8 font-mono'
              value={draft.pattern}
              onChange={(e) => set('pattern', e.target.value)}
              required
            />
          </Field>
          {kind === 'alias' ? (
            <Field label={t('p6.use')}>
              <Input
                className='h-8'
                value={draft.to}
                onChange={(e) => set('to', e.target.value)}
                required
              />
            </Field>
          ) : (
            <Field label={t('p6.source')}>
              <SelectField
                value={draft.source}
                onChange={(v) => set('source', v ?? 'name')}
                options={SOURCES.map((s) => ({ value: s, label: s }))}
              />
            </Field>
          )}
        </>
      )}
      <Button type='submit' size='sm' disabled={create.isPending}>
        <Plus className='size-4' />
        {t('p6.add_rule')}
      </Button>
    </form>
  )
}

function Tester({ projectId }: { projectId: number }) {
  const { t } = useTranslation()
  const { test } = useRuleActions(projectId)
  const [samples, setSamples] = useState(
    '101 / B / 305\n101 / SCA-Dism / 512-21 Shut'
  )
  const [pattern, setPattern] = useState('')
  const [results, setResults] = useState<RuleTestResult[]>([])
  return (
    <div className='grid gap-2 rounded-lg border p-3'>
      <p className='text-sm font-medium'>{t('p6.test_title')}</p>
      <Textarea
        rows={4}
        className='font-mono text-xs'
        value={samples}
        onChange={(e) => setSamples(e.target.value)}
        aria-label={t('p6.samples')}
      />
      <div className='flex flex-wrap gap-2'>
        <Input
          className='h-8 flex-1 font-mono text-xs'
          value={pattern}
          onChange={(e) => setPattern(e.target.value)}
          placeholder={t('p6.try_pattern')}
        />
        <Button
          size='sm'
          variant='outline'
          onClick={() =>
            test.mutate(
              { samples: parseSamples(samples), pattern: pattern || null },
              { onSuccess: setResults }
            )
          }
        >
          <FlaskConical className='size-4' />
          {t('p6.test')}
        </Button>
      </div>
      {results.length ? (
        <div className='overflow-x-auto'>
          <table className='w-full text-xs'>
            <thead className='text-muted-foreground'>
              <tr className='text-start'>
                <th className='p-1 text-start'>{t('p6.sample')}</th>
                <th className='p-1 text-start'>{t('p6.groups')}</th>
                <th className='p-1 text-start'>{t('p6.result')}</th>
              </tr>
            </thead>
            <tbody>
              {results.map((r, i) => (
                <tr key={i} className='border-t align-top'>
                  <td className='p-1 font-mono'>{r.sample}</td>
                  <td className='p-1 font-mono'>
                    {r.groups
                      ? Object.entries(r.groups)
                          .map(([k, v]) => `${k}=${v}`)
                          .join(' ')
                      : '—'}
                    {r.window ? ` window=${r.window}` : ''}
                  </td>
                  <td className='p-1'>
                    <strong>{r.resolution}</strong>{' '}
                    {r.node_path ?? r.reason ?? r.ineligible_reason ?? ''}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  )
}

function CriticalSetting({ projectId }: { projectId: number }) {
  const { t } = useTranslation()
  const { query, save } = useP6Settings(projectId)
  if (!query.data) return null
  const s = query.data
  return (
    <div className='flex flex-wrap items-end gap-2 rounded-lg border p-3'>
      <Field label={t('p6.critical')} className='w-56'>
        <SelectField
          value={s.critical_definition ?? 'total_float_le'}
          onChange={(v) =>
            save.mutate({
              ...s,
              critical_definition: (v ?? 'total_float_le') as never,
            })
          }
          options={[
            { value: 'total_float_le', label: t('p6.critical.float') },
            { value: 'longest_path', label: t('p6.critical.longest') },
          ]}
        />
      </Field>
      <Field label={t('p6.float_hours')} className='w-32'>
        <Input
          className='h-8'
          type='number'
          defaultValue={s.critical_float_hours ?? 0}
          onBlur={(e) =>
            save.mutate({ ...s, critical_float_hours: Number(e.target.value) })
          }
        />
      </Field>
    </div>
  )
}

/** Grammar, eligibility and alias rules, with a test bench for sample names. */
export function RulesTab({ projectId }: { projectId: number }) {
  const { t } = useTranslation()
  const { data: rules = [] } = useRules(projectId)
  const { update, remove } = useRuleActions(projectId)
  return (
    <div className='flex flex-col gap-3'>
      {KINDS.map((kind) => (
        <section key={kind} className='grid gap-1'>
          <h3 className='text-sm font-semibold'>{t(`p6.kind.${kind}`)}</h3>
          {rules
            .filter((r) => r.kind === kind)
            .map((r) => (
              <div
                key={r.id}
                className='flex items-center gap-2 rounded-md border px-2 py-1 text-sm'
              >
                <Switch
                  checked={r.enabled}
                  aria-label={t('p6.enabled')}
                  onCheckedChange={(v) =>
                    update.mutate({ id: r.id, body: { enabled: v } })
                  }
                />
                <span className='font-medium'>{r.name}</span>
                <span className='flex-1 truncate font-mono text-xs text-muted-foreground'>
                  {describe(r)}
                </span>
                <Button
                  size='icon'
                  variant='ghost'
                  className='size-7'
                  aria-label={t('p6.delete')}
                  onClick={() => remove.mutate(r.id)}
                >
                  <Trash2 className='size-4' />
                </Button>
              </div>
            ))}
        </section>
      ))}
      <NewRule projectId={projectId} />
      <Tester projectId={projectId} />
      <CriticalSetting projectId={projectId} />
    </div>
  )
}
