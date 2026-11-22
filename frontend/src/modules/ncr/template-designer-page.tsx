import { useState } from 'react'
import { ArrowDown, ArrowUp, Copy, Plus, Trash2, Upload } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { useCurrentProject } from '@/stores/use-current-project'
import { can, useSession } from '@/lib/session'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Page } from '@/components/layout/page'
import { NativeSelect } from '@/components/native-select'
import { StatusBadge } from '@/components/records/status-badge'
import {
  COMPLETION_EFFECTS,
  MDR_EFFECTS,
  ORIGINS,
  PUNCH_CATEGORIES,
  type Revision,
  SEVERITIES,
  type Template,
  type TemplateBody,
  VISIBILITIES,
  useCategories,
  useCopyTemplate,
  useCreateTemplate,
  useDefaults,
  usePublish,
  usePutCategory,
  usePutDefault,
  useSaveDraft,
  useTemplate,
  useTemplates,
} from './api'
import {
  FIELD_TYPES,
  type FieldDef,
  type IssueType,
  STEPS,
  fieldProblems,
  keyFromLabel,
} from './workflow'

type Draft = TemplateBody & { fields: FieldDef[] }

function draftOf(rev: Revision): Draft {
  return {
    name: rev.name,
    fields: rev.fields.map((f) => ({ ...f })),
    default_origin: rev.default_origin,
    default_visibility: rev.default_visibility,
    default_mdr_effect: rev.default_mdr_effect,
    completion_effect: rev.completion_effect,
    default_severity: rev.default_severity,
    default_punch_category: rev.default_punch_category,
    separate_close: rev.separate_close,
  }
}

/** The field list editor: one row per field, reorder, add, remove. */
export function FieldListEditor({
  type,
  fields,
  onChange,
  disabled,
}: {
  type: IssueType
  fields: FieldDef[]
  onChange: (fields: FieldDef[]) => void
  disabled?: boolean
}) {
  const { t } = useTranslation()
  const update = (i: number, patch: Partial<FieldDef>) =>
    onChange(fields.map((f, j) => (j === i ? { ...f, ...patch } : f)))
  const swap = (i: number, j: number) => {
    const next = [...fields]
    ;[next[i], next[j]] = [next[j], next[i]]
    onChange(next)
  }
  return (
    <div className='grid gap-2'>
      {fields.map((f, i) => (
        <div
          key={i}
          className='grid gap-2 rounded-md border p-2 md:grid-cols-[1fr_9rem_8rem_9rem_auto]'
        >
          <Input
            aria-label={t('issues.designer.label')}
            placeholder={t('issues.designer.label')}
            disabled={disabled}
            value={f.label}
            onChange={(e) => update(i, { label: e.target.value })}
          />
          <Input
            aria-label={t('issues.designer.key')}
            className='font-mono text-xs'
            disabled={disabled}
            value={f.key}
            onChange={(e) => update(i, { key: e.target.value })}
          />
          <NativeSelect
            aria-label={t('issues.designer.type')}
            disabled={disabled}
            values={FIELD_TYPES}
            value={f.type}
            onChange={(e) =>
              update(i, { type: e.target.value as FieldDef['type'] })
            }
          />
          <NativeSelect
            aria-label={t('issues.designer.step')}
            disabled={disabled}
            values={STEPS[type]}
            value={f.step}
            onChange={(e) => update(i, { step: e.target.value })}
          />
          <div className='flex items-center gap-1'>
            <label className='flex items-center gap-1 text-xs'>
              <Checkbox
                disabled={disabled}
                checked={Boolean(f.required)}
                onCheckedChange={(v) => update(i, { required: v === true })}
              />
              {t('issues.designer.required')}
            </label>
            <Button
              size='icon'
              variant='ghost'
              aria-label={t('issues.designer.up')}
              disabled={disabled || i === 0}
              onClick={() => swap(i, i - 1)}
            >
              <ArrowUp />
            </Button>
            <Button
              size='icon'
              variant='ghost'
              aria-label={t('issues.designer.down')}
              disabled={disabled || i === fields.length - 1}
              onClick={() => swap(i, i + 1)}
            >
              <ArrowDown />
            </Button>
            <Button
              size='icon'
              variant='ghost'
              aria-label={t('issues.designer.remove')}
              disabled={disabled}
              onClick={() => onChange(fields.filter((_, j) => j !== i))}
            >
              <Trash2 />
            </Button>
          </div>
          {f.type === 'select' || f.type === 'multiselect' ? (
            <Input
              className='md:col-span-5'
              aria-label={t('issues.designer.options')}
              placeholder={t('issues.designer.options')}
              disabled={disabled}
              value={(f.options ?? []).join(', ')}
              onChange={(e) =>
                update(i, {
                  options: e.target.value
                    .split(',')
                    .map((o) => o.trim())
                    .filter(Boolean),
                })
              }
            />
          ) : null}
        </div>
      ))}
      {disabled ? null : (
        <Button
          size='sm'
          variant='outline'
          className='w-fit'
          onClick={() =>
            onChange([
              ...fields,
              {
                key: keyFromLabel(
                  'new field',
                  fields.map((f) => f.key)
                ),
                label: '',
                type: 'text',
                step: 'raise',
              },
            ])
          }
        >
          <Plus /> {t('issues.designer.add_field')}
        </Button>
      )}
    </div>
  )
}

function Select({
  id,
  label,
  values,
  value,
  onChange,
  disabled,
  placeholder,
}: {
  id: string
  label: string
  values: readonly string[]
  value: string | null | undefined
  onChange: (v: string | null) => void
  disabled?: boolean
  placeholder?: string
}) {
  return (
    <div className='grid gap-1.5'>
      <Label htmlFor={id}>{label}</Label>
      <NativeSelect
        id={id}
        values={values}
        placeholder={placeholder}
        disabled={disabled}
        value={value ?? ''}
        onChange={(e) => onChange(e.target.value || null)}
      />
    </div>
  )
}

function Editor({
  template,
  projectId,
}: {
  template: Template
  projectId: number | null
}) {
  const { t } = useTranslation()
  const session = useSession()
  const source = template.draft ?? template.published
  const [draft, setDraft] = useState<Draft | null>(
    source ? draftOf(source) : null
  )
  const save = useSaveDraft(template.id)
  const publish = usePublish(template.id)
  const copy = useCopyTemplate(projectId ?? 0)
  const writable =
    template.layer === 'project'
      ? can(session, 'ncr.manage')
      : can(session, 'ncr.configure')
  if (!draft) return null
  const set = (patch: Partial<Draft>) => setDraft({ ...draft, ...patch })
  const problems = fieldProblems(template.issue_type, draft.fields)
  return (
    <div className='grid gap-4'>
      <div className='flex flex-wrap items-center gap-2'>
        <h3 className='text-lg font-semibold'>{template.name}</h3>
        <StatusBadge status={template.issue_type} />
        <StatusBadge status={template.layer} />
        <span className='text-xs text-muted-foreground'>
          {template.published
            ? t('issues.designer.published_rev', {
                n: template.published.number,
              })
            : t('issues.designer.unpublished')}
          {template.draft
            ? ` · ${t('issues.designer.draft_rev', { n: template.draft.number })}`
            : ''}
        </span>
        {template.layer === 'library' &&
        projectId &&
        can(session, 'ncr.manage') ? (
          <Button
            size='sm'
            variant='outline'
            className='ms-auto'
            onClick={() =>
              copy.mutate(template.id, {
                onSuccess: () => toast.success(t('issues.designer.copied')),
              })
            }
          >
            <Copy /> {t('issues.designer.copy')}
          </Button>
        ) : null}
      </div>
      <div className='grid gap-3 sm:grid-cols-3'>
        <div className='grid gap-1.5 sm:col-span-3'>
          <Label htmlFor='tpl-name'>{t('issues.designer.name')}</Label>
          <Input
            id='tpl-name'
            disabled={!writable}
            value={draft.name ?? ''}
            onChange={(e) => set({ name: e.target.value })}
          />
        </div>
        <Select
          id='tpl-origin'
          label={t('issues.origin')}
          values={ORIGINS}
          value={draft.default_origin}
          onChange={(v) => set({ default_origin: v ?? 'qa' })}
          disabled={!writable}
        />
        <Select
          id='tpl-vis'
          label={t('issues.flag.visibility')}
          values={VISIBILITIES}
          value={draft.default_visibility}
          onChange={(v) => set({ default_visibility: v ?? 'internal' })}
          disabled={!writable}
        />
        <Select
          id='tpl-mdr'
          label={t('issues.flag.mdr_effect')}
          values={MDR_EFFECTS}
          value={draft.default_mdr_effect}
          onChange={(v) => set({ default_mdr_effect: v ?? 'blocks' })}
          disabled={!writable}
        />
        {template.issue_type === 'ncr' ? (
          <>
            <Select
              id='tpl-comp'
              label={t('issues.flag.completion_effect')}
              values={COMPLETION_EFFECTS}
              value={draft.completion_effect}
              onChange={(v) => set({ completion_effect: v ?? 'blocks' })}
              disabled={!writable}
            />
            <Select
              id='tpl-sev'
              label={t('issues.severity')}
              values={SEVERITIES}
              value={draft.default_severity}
              onChange={(v) => set({ default_severity: v })}
              placeholder='—'
              disabled={!writable}
            />
          </>
        ) : (
          <>
            <Select
              id='tpl-cat'
              label={t('issues.punch_category')}
              values={PUNCH_CATEGORIES}
              value={draft.default_punch_category}
              onChange={(v) => set({ default_punch_category: v })}
              placeholder='—'
              disabled={!writable}
            />
            <label className='flex items-center gap-2 self-end pb-2 text-sm'>
              <Checkbox
                disabled={!writable}
                checked={Boolean(draft.separate_close)}
                onCheckedChange={(v) => set({ separate_close: v === true })}
              />
              {t('issues.designer.separate_close')}
            </label>
          </>
        )}
      </div>
      <div className='grid gap-2'>
        <h4 className='text-sm font-semibold'>{t('issues.designer.fields')}</h4>
        <FieldListEditor
          type={template.issue_type}
          fields={draft.fields}
          onChange={(fields) => set({ fields })}
          disabled={!writable}
        />
      </div>
      {problems.length ? (
        <ul className='list-disc ps-5 text-sm text-red-600'>
          {problems.map((p) => (
            <li key={p}>{p}</li>
          ))}
        </ul>
      ) : null}
      {writable ? (
        <div className='flex gap-2'>
          <Button
            disabled={save.isPending || problems.length > 0}
            onClick={() =>
              save.mutate(draft, {
                onSuccess: () => toast.success(t('issues.designer.saved')),
              })
            }
          >
            {t('issues.designer.save_draft')}
          </Button>
          <Button
            variant='outline'
            disabled={!template.draft || publish.isPending}
            onClick={() =>
              publish.mutate(undefined, {
                onSuccess: () => toast.success(t('issues.designer.published')),
              })
            }
          >
            <Upload /> {t('issues.designer.publish')}
          </Button>
        </div>
      ) : null}
    </div>
  )
}

function NewTemplate({
  projectId,
  onMade,
}: {
  projectId: number | null
  onMade: (id: number) => void
}) {
  const { t } = useTranslation()
  const create = useCreateTemplate()
  const { data: categories = [] } = useCategories(projectId)
  const [type, setType] = useState<IssueType>('punch')
  const [name, setName] = useState('')
  const [category, setCategory] = useState('general')
  return (
    <form
      className='grid gap-2 rounded-md border border-dashed p-3'
      onSubmit={(e) => {
        e.preventDefault()
        create.mutate(
          { project_id: projectId, name, issue_type: type, category },
          {
            onSuccess: (made) => {
              setName('')
              onMade(made.id)
            },
          }
        )
      }}
    >
      <div className='flex gap-1' role='radiogroup'>
        {(['punch', 'ncr'] as const).map((v) => (
          <button
            key={v}
            type='button'
            role='radio'
            aria-checked={type === v}
            className={cn(
              'flex-1 rounded-md border px-2 py-1 text-sm',
              type === v && 'border-primary bg-primary text-primary-foreground'
            )}
            onClick={() => setType(v)}
          >
            {t(`issues.tab.${v}`)}
          </button>
        ))}
      </div>
      <Input
        required
        aria-label={t('issues.designer.name')}
        placeholder={t('issues.designer.name')}
        value={name}
        onChange={(e) => setName(e.target.value)}
      />
      <NativeSelect
        aria-label={t('issues.category')}
        options={categories.map((c) => ({ value: c.key, label: c.label }))}
        value={category}
        onChange={(e) => setCategory(e.target.value)}
      />
      <Button size='sm' type='submit' disabled={create.isPending}>
        <Plus /> {t('issues.designer.new')}
      </Button>
    </form>
  )
}

function CategoriesAndDefaults({
  projectId,
  templates,
}: {
  projectId: number | null
  templates: Template[]
}) {
  const { t } = useTranslation()
  const session = useSession()
  const { data: categories = [] } = useCategories(projectId)
  const { data: defaults = [] } = useDefaults(projectId)
  const put = usePutCategory(projectId)
  const putDefault = usePutDefault()
  const writable = can(session, projectId ? 'ncr.manage' : 'ncr.configure')
  const [newKey, setNewKey] = useState('')
  return (
    <details className='rounded-md border p-3 text-sm'>
      <summary className='cursor-pointer font-medium'>
        {t('issues.designer.categories')}
      </summary>
      <table className='mt-2 w-full text-left'>
        <thead className='text-xs text-muted-foreground'>
          <tr>
            <th>{t('issues.category')}</th>
            <th>{t('issues.designer.active')}</th>
            <th>{t('issues.designer.project_level')}</th>
            <th>{t('issues.tab.punch')}</th>
            <th>{t('issues.tab.ncr')}</th>
          </tr>
        </thead>
        <tbody>
          {categories.map((c) => (
            <tr key={c.key} className='border-t'>
              <td className='py-1'>
                {c.label}{' '}
                <span className='text-xs text-muted-foreground'>
                  ({c.layer})
                </span>
              </td>
              <td>
                <Checkbox
                  disabled={!writable}
                  checked={c.is_active}
                  onCheckedChange={(v) =>
                    put.mutate({ key: c.key, body: { is_active: v === true } })
                  }
                />
              </td>
              <td>
                <Checkbox
                  disabled={!writable}
                  checked={c.allows_project_level}
                  onCheckedChange={(v) =>
                    put.mutate({
                      key: c.key,
                      body: { allows_project_level: v === true },
                    })
                  }
                />
              </td>
              {(['punch', 'ncr'] as const).map((type) => (
                <td key={type}>
                  <NativeSelect
                    className='h-7 text-xs'
                    aria-label={`${c.label} ${type}`}
                    disabled={!writable}
                    placeholder='—'
                    options={templates
                      .filter((tp) => tp.issue_type === type && tp.published)
                      .map((tp) => ({ value: String(tp.id), label: tp.name }))}
                    value={String(
                      defaults.find(
                        (d) => d.category === c.key && d.issue_type === type
                      )?.template_id ?? ''
                    )}
                    onChange={(e) =>
                      e.target.value &&
                      putDefault.mutate({
                        project_id: projectId,
                        category: c.key,
                        issue_type: type,
                        template_id: Number(e.target.value),
                      })
                    }
                  />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {writable ? (
        <form
          className='mt-2 flex gap-2'
          onSubmit={(e) => {
            e.preventDefault()
            const key = keyFromLabel(newKey)
            put.mutate(
              { key, body: { label: newKey } },
              { onSuccess: () => setNewKey('') }
            )
          }}
        >
          <Input
            className='h-8 w-60'
            aria-label={t('issues.designer.new_category')}
            placeholder={t('issues.designer.new_category')}
            value={newKey}
            onChange={(e) => setNewKey(e.target.value)}
          />
          <Button size='sm' type='submit' disabled={!newKey.trim()}>
            <Plus />
          </Button>
        </form>
      ) : null}
    </details>
  )
}

export default function TemplateDesignerPage() {
  const { t } = useTranslation()
  const project = useCurrentProject()
  const session = useSession()
  const projectId = project?.id ?? null
  const [type, setType] = useState<IssueType | ''>('')
  const { data: templates = [] } = useTemplates(projectId, type || undefined)
  const [selected, setSelected] = useState<number | null>(null)
  const { data: template } = useTemplate(selected)
  return (
    <Page
      title={t('issues.templates')}
      description={t('issues.designer.description')}
      projectScoped
    >
      <CategoriesAndDefaults projectId={projectId} templates={templates} />
      <div className='grid gap-4 md:grid-cols-[18rem_1fr]'>
        <div className='grid content-start gap-2'>
          <NativeSelect
            aria-label={t('issues.designer.type')}
            placeholder={t('issues.designer.all_types')}
            values={['punch', 'ncr']}
            value={type}
            onChange={(e) => setType(e.target.value as IssueType | '')}
          />
          {can(session, projectId ? 'ncr.manage' : 'ncr.configure') ? (
            <NewTemplate projectId={projectId} onMade={setSelected} />
          ) : null}
          <ul className='grid gap-1'>
            {templates.map((tp) => (
              <li key={tp.id}>
                <button
                  className={cn(
                    'flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-start text-sm hover:bg-muted',
                    selected === tp.id && 'bg-muted font-medium'
                  )}
                  onClick={() => setSelected(tp.id)}
                >
                  <span className='flex-1 truncate'>{tp.name}</span>
                  <span className='text-xs text-muted-foreground'>
                    {tp.layer === 'library' ? 'lib' : 'proj'}
                    {tp.draft ? ' · draft' : ''}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </div>
        <div>
          {template ? (
            <Editor
              key={`${template.id}-${template.draft?.id ?? template.published?.id}`}
              template={template}
              projectId={projectId}
            />
          ) : (
            <p className='text-sm text-muted-foreground'>
              {t('issues.designer.pick')}
            </p>
          )}
        </div>
      </div>
    </Page>
  )
}
