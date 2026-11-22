import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { NativeSelect, UserSelect } from '@/components/native-select'
import {
  PUNCH_CATEGORIES,
  SEVERITIES,
  type Template,
  useCategories,
  useCreateIssue,
  useDefaults,
  useNodeOptions,
  useTemplates,
} from './api'
import { type Answers, PhotoInput, TemplateFields } from './template-fields'
import type { IssueType } from './workflow'

/** The template a raise starts from: the category's default, else the first published one. */
function useTemplateChoice(
  projectId: number,
  type: IssueType,
  category: string
) {
  const { data: templates = [] } = useTemplates(projectId, type, category)
  const { data: defaults = [] } = useDefaults(projectId)
  const usable = templates.filter((tp) => tp.published && tp.is_active)
  const mapped = defaults.find(
    (d) => d.category === category && d.issue_type === type
  )?.template_id
  const fallback =
    usable.find((tp) => tp.id === mapped) ??
    usable.find((tp) => tp.derived_from_id === mapped) ??
    usable[0]
  return { usable, fallback }
}

function AnchorPicker({
  projectId,
  value,
  onChange,
}: {
  projectId: number
  value: number | null
  onChange: (id: number | null) => void
}) {
  const { t } = useTranslation()
  const [search, setSearch] = useState('')
  const { data: nodes = [] } = useNodeOptions(projectId, search)
  return (
    <div className='grid gap-1.5'>
      <Label htmlFor='issue-anchor'>{t('issues.anchor')}</Label>
      <div className='flex gap-2'>
        <Input
          className='w-32'
          aria-label={t('issues.search_nodes')}
          placeholder={t('issues.search_nodes')}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <NativeSelect
          id='issue-anchor'
          placeholder={t('issues.project_level')}
          options={nodes.map((n) => ({ value: String(n.id), label: n.label }))}
          value={value ? String(value) : ''}
          onChange={(e) =>
            onChange(e.target.value ? Number(e.target.value) : null)
          }
        />
      </div>
    </div>
  )
}

function CategorySelect({
  projectId,
  value,
  onChange,
}: {
  projectId: number
  value: string
  onChange: (key: string) => void
}) {
  const { t } = useTranslation()
  const { data: categories = [] } = useCategories(projectId)
  return (
    <div className='grid gap-1.5'>
      <Label htmlFor='issue-category'>{t('issues.category')}</Label>
      <NativeSelect
        id='issue-category'
        options={categories
          .filter((c) => c.is_active)
          .map((c) => ({ value: c.key, label: c.label }))}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
    </div>
  )
}

const CAT_TONE: Record<string, string> = {
  A: 'data-[on=true]:bg-red-600 data-[on=true]:text-white',
  B: 'data-[on=true]:bg-amber-500 data-[on=true]:text-white',
  C: 'data-[on=true]:bg-sky-600 data-[on=true]:text-white',
}

/** Quick punch capture: photo first, one line of text, Cat A/B/C, where. Big targets for a phone. */
export function QuickPunch({
  projectId,
  onClose,
  onCreated,
}: {
  projectId: number
  onClose: () => void
  onCreated: (id: number) => void
}) {
  const { t } = useTranslation()
  const create = useCreateIssue()
  const [category, setCategory] = useState('general')
  const { fallback } = useTemplateChoice(projectId, 'punch', category)
  const [photos, setPhotos] = useState<number[]>([])
  const [title, setTitle] = useState('')
  const [cat, setCat] = useState<string>('B')
  const [anchor, setAnchor] = useState<number | null>(null)
  const [responsible, setResponsible] = useState<number | null>(null)
  const photoKey = fallback?.published?.fields.find(
    (f) => f.type === 'photo' && f.step === 'raise'
  )?.key
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className='max-h-[95dvh] overflow-y-auto sm:max-w-md'>
        <DialogHeader>
          <DialogTitle>{t('issues.quick_punch')}</DialogTitle>
        </DialogHeader>
        <form
          id='quick-punch'
          className='grid gap-4'
          onSubmit={(e) => {
            e.preventDefault()
            create.mutate(
              {
                project_id: projectId,
                issue_type: 'punch',
                template_id: fallback?.id ?? null,
                category,
                title,
                punch_category: cat as never,
                source: 'walkdown',
                links: [],
                anchor_node_id: anchor,
                responsible_user_id: responsible,
                answers:
                  photoKey && photos.length ? { [photoKey]: photos } : {},
              },
              {
                onSuccess: (made) => {
                  onClose()
                  onCreated(made.id)
                },
              }
            )
          }}
        >
          <PhotoInput
            value={photos}
            onChange={setPhotos}
            projectId={projectId}
            disabled={!photoKey}
            label={t('issues.take_photo')}
          />
          <div className='grid gap-1.5'>
            <Label htmlFor='quick-title'>{t('issues.what_is_wrong')}</Label>
            <Input
              id='quick-title'
              required
              autoFocus
              className='h-11 text-base'
              value={title}
              onChange={(e) => setTitle(e.target.value)}
            />
          </div>
          <div
            className='grid grid-cols-3 gap-2'
            role='radiogroup'
            aria-label={t('issues.punch_category')}
          >
            {PUNCH_CATEGORIES.map((c) => (
              <button
                key={c}
                type='button'
                role='radio'
                aria-checked={cat === c}
                data-on={cat === c}
                className={cn(
                  'grid h-14 place-items-center rounded-md border text-sm font-medium',
                  CAT_TONE[c]
                )}
                onClick={() => setCat(c)}
              >
                <span className='text-lg'>Cat {c}</span>
                <span className='text-[10px] opacity-80'>
                  {t(`issues.cat_short.${c}`)}
                </span>
              </button>
            ))}
          </div>
          <CategorySelect
            projectId={projectId}
            value={category}
            onChange={setCategory}
          />
          <AnchorPicker
            projectId={projectId}
            value={anchor}
            onChange={setAnchor}
          />
          <div className='grid gap-1.5'>
            <Label>{t('issues.responsible')}</Label>
            <UserSelect value={responsible} onChange={setResponsible} />
          </div>
        </form>
        <DialogFooter>
          <Button
            type='submit'
            form='quick-punch'
            className='h-11 w-full'
            disabled={create.isPending || !fallback}
          >
            {t('issues.raise')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/** Raise any issue from a template, with the template's raise-step fields. */
export function RaiseIssue({
  projectId,
  type,
  onClose,
  onCreated,
}: {
  projectId: number
  type: IssueType
  onClose: () => void
  onCreated: (id: number) => void
}) {
  const { t } = useTranslation()
  const create = useCreateIssue()
  const [category, setCategory] = useState('general')
  const { usable, fallback } = useTemplateChoice(projectId, type, category)
  const [picked, setPicked] = useState<number | null>(null)
  const template: Template | undefined =
    usable.find((tp) => tp.id === picked) ?? fallback
  const [draft, setDraft] = useState({
    title: '',
    description: '',
    severity: '',
    punch_category: '',
    anchor: null as number | null,
    responsible: null as number | null,
    due_date: '',
  })
  const [answers, setAnswers] = useState<Answers>({})
  const raiseFields = useMemo(
    () =>
      (template?.published?.fields ?? []).filter((f) =>
        ['raise', 'containment'].includes(f.step)
      ),
    [template]
  )
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className='max-h-[95dvh] overflow-y-auto sm:max-w-2xl'>
        <DialogHeader>
          <DialogTitle>
            {t(type === 'ncr' ? 'issues.raise_ncr' : 'issues.raise_punch')}
          </DialogTitle>
        </DialogHeader>
        <form
          id='raise-issue'
          className='grid gap-3'
          onSubmit={(e) => {
            e.preventDefault()
            create.mutate(
              {
                project_id: projectId,
                issue_type: type,
                template_id: template?.id ?? null,
                category,
                title: draft.title,
                description: draft.description || null,
                severity: (draft.severity || null) as never,
                punch_category: (draft.punch_category || null) as never,
                anchor_node_id: draft.anchor,
                responsible_user_id: draft.responsible,
                due_date: draft.due_date || null,
                source: 'other',
                links: [],
                answers: Object.fromEntries(
                  Object.entries(answers).filter(
                    ([, v]) => v !== null && v !== ''
                  )
                ),
              },
              {
                onSuccess: (made) => {
                  onClose()
                  onCreated(made.id)
                },
              }
            )
          }}
        >
          <div className='grid gap-3 sm:grid-cols-2'>
            <CategorySelect
              projectId={projectId}
              value={category}
              onChange={(c) => {
                setCategory(c)
                setPicked(null)
              }}
            />
            <div className='grid gap-1.5'>
              <Label htmlFor='raise-template'>{t('issues.template')}</Label>
              <NativeSelect
                id='raise-template'
                options={usable.map((tp) => ({
                  value: String(tp.id),
                  label: tp.name,
                }))}
                value={template ? String(template.id) : ''}
                onChange={(e) => setPicked(Number(e.target.value))}
              />
            </div>
            <div className='grid gap-1.5 sm:col-span-2'>
              <Label htmlFor='raise-title'>{t('issues.title_field')}</Label>
              <Input
                id='raise-title'
                required
                value={draft.title}
                onChange={(e) => setDraft({ ...draft, title: e.target.value })}
              />
            </div>
            <div className='grid gap-1.5 sm:col-span-2'>
              <Label htmlFor='raise-desc'>{t('issues.description')}</Label>
              <Textarea
                id='raise-desc'
                value={draft.description}
                onChange={(e) =>
                  setDraft({ ...draft, description: e.target.value })
                }
              />
            </div>
            {type === 'ncr' ? (
              <div className='grid gap-1.5'>
                <Label htmlFor='raise-sev'>{t('issues.severity')}</Label>
                <NativeSelect
                  id='raise-sev'
                  placeholder={t('issues.template_default')}
                  values={SEVERITIES}
                  value={draft.severity}
                  onChange={(e) =>
                    setDraft({ ...draft, severity: e.target.value })
                  }
                />
              </div>
            ) : (
              <div className='grid gap-1.5'>
                <Label htmlFor='raise-cat'>{t('issues.punch_category')}</Label>
                <NativeSelect
                  id='raise-cat'
                  placeholder={t('issues.template_default')}
                  options={PUNCH_CATEGORIES.map((c) => ({
                    value: c,
                    label: t(`issues.cat.${c}`),
                  }))}
                  value={draft.punch_category}
                  onChange={(e) =>
                    setDraft({ ...draft, punch_category: e.target.value })
                  }
                />
              </div>
            )}
            <div className='grid gap-1.5'>
              <Label htmlFor='raise-due'>{t('issues.due')}</Label>
              <Input
                id='raise-due'
                type='date'
                value={draft.due_date}
                onChange={(e) =>
                  setDraft({ ...draft, due_date: e.target.value })
                }
              />
            </div>
            <AnchorPicker
              projectId={projectId}
              value={draft.anchor}
              onChange={(anchor) => setDraft({ ...draft, anchor })}
            />
            <div className='grid gap-1.5'>
              <Label>{t('issues.responsible')}</Label>
              <UserSelect
                value={draft.responsible}
                onChange={(responsible) => setDraft({ ...draft, responsible })}
              />
            </div>
          </div>
          {raiseFields.length ? (
            <TemplateFields
              fields={raiseFields}
              values={answers}
              onChange={(key, value) =>
                setAnswers({ ...answers, [key]: value })
              }
              editable={() => true}
              projectId={projectId}
            />
          ) : null}
        </form>
        <DialogFooter>
          <Button
            type='submit'
            form='raise-issue'
            disabled={create.isPending || !template}
          >
            {t('issues.raise')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
