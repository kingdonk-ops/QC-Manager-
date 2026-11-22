import { useState } from 'react'
import { Link } from '@tanstack/react-router'
import {
  ArrowDown,
  ArrowLeft,
  ArrowUp,
  Copy,
  GripVertical,
  Plus,
  Save,
  Sparkles,
  Trash2,
} from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { useCurrentProject } from '@/stores/use-current-project'
import { can, useSession } from '@/lib/session'
import { cn } from '@/lib/utils'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Page } from '@/components/layout/page'
import { NativeSelect } from '@/components/native-select'
import {
  type Template,
  type TemplateBody,
  type TemplateItem,
  type TemplateSection,
  useSaveTemplate,
  useTemplateAction,
  useTemplates,
} from './api'
import { ItpEditor, TemplateSettingsFields } from './itp-editor'
import { PointBadges } from './signoff'

type Draft = Omit<TemplateBody, 'project_id'>

const blankItem = (): TemplateItem => ({
  text: '',
  response_type: 'pass_fail',
  unit: null,
  min_value: null,
  max_value: null,
  requires_photo_on_fail: false,
  guidance: null,
})

const blank = (): Draft => ({
  name: '',
  trade: '',
  activity: '',
  description: '',
  active: true,
  sections: [{ title: 'General', items: [blankItem()] }],
  kind: 'inspection',
  area: 'general',
  is_formal: false,
  linked_issue_types: [],
  requires_client_signature: false,
  activities: [],
})

function move<T>(list: T[], from: number, to: number): T[] {
  if (to < 0 || to >= list.length || from === to) return list
  const next = [...list]
  const [moved] = next.splice(from, 1)
  next.splice(to, 0, moved)
  return next
}

const num = (v: string) => (v.trim() === '' ? null : Number(v))

function ItemEditor({
  item,
  onChange,
  onRemove,
  onMove,
  dragProps,
}: {
  item: TemplateItem
  onChange: (item: TemplateItem) => void
  onRemove: () => void
  onMove: (delta: number) => void
  dragProps: React.HTMLAttributes<HTMLDivElement>
}) {
  const { t } = useTranslation()
  const numeric = item.response_type === 'numeric'
  return (
    <div className='grid gap-2 rounded-md border bg-card p-3' {...dragProps}>
      <div className='flex items-start gap-2'>
        <GripVertical
          className='mt-2 size-4 shrink-0 cursor-grab text-muted-foreground'
          aria-label={t('inspections.drag')}
        />
        <Input
          aria-label={t('inspections.item_text')}
          placeholder={t('inspections.item_text')}
          value={item.text}
          onChange={(e) => onChange({ ...item, text: e.target.value })}
        />
        <NativeSelect
          className='w-48 shrink-0'
          aria-label={t('inspections.response_type')}
          options={[
            { value: 'pass_fail', label: t('inspections.pass_fail_na') },
            { value: 'numeric', label: t('inspections.numeric') },
          ]}
          value={item.response_type ?? 'pass_fail'}
          onChange={(e) =>
            onChange({
              ...item,
              response_type: e.target.value as TemplateItem['response_type'],
            })
          }
        />
        <div className='flex'>
          <Button
            size='icon'
            variant='ghost'
            aria-label={t('inspections.move_up')}
            onClick={() => onMove(-1)}
          >
            <ArrowUp />
          </Button>
          <Button
            size='icon'
            variant='ghost'
            aria-label={t('inspections.move_down')}
            onClick={() => onMove(1)}
          >
            <ArrowDown />
          </Button>
          <Button
            size='icon'
            variant='ghost'
            aria-label={t('inspections.delete')}
            onClick={onRemove}
          >
            <Trash2 />
          </Button>
        </div>
      </div>
      <div className='flex flex-wrap items-center gap-2 ps-6'>
        {numeric ? (
          <>
            <Input
              className='h-8 w-20'
              placeholder={t('inspections.unit')}
              aria-label={t('inspections.unit')}
              value={item.unit ?? ''}
              onChange={(e) =>
                onChange({ ...item, unit: e.target.value || null })
              }
            />
            <Input
              className='h-8 w-24'
              type='number'
              step='any'
              placeholder={t('inspections.min')}
              aria-label={t('inspections.min')}
              value={item.min_value ?? ''}
              onChange={(e) =>
                onChange({ ...item, min_value: num(e.target.value) })
              }
            />
            <Input
              className='h-8 w-24'
              type='number'
              step='any'
              placeholder={t('inspections.max')}
              aria-label={t('inspections.max')}
              value={item.max_value ?? ''}
              onChange={(e) =>
                onChange({ ...item, max_value: num(e.target.value) })
              }
            />
          </>
        ) : null}
        <label className='flex items-center gap-1.5 text-sm'>
          <Checkbox
            checked={Boolean(item.requires_photo_on_fail)}
            onCheckedChange={(v) =>
              onChange({ ...item, requires_photo_on_fail: v === true })
            }
          />
          {t('inspections.photo_on_fail_label')}
        </label>
        <Input
          className='h-8 min-w-48 flex-1'
          placeholder={t('inspections.guidance')}
          aria-label={t('inspections.guidance')}
          value={item.guidance ?? ''}
          onChange={(e) =>
            onChange({ ...item, guidance: e.target.value || null })
          }
        />
      </div>
    </div>
  )
}

function SectionEditor({
  section,
  onChange,
  onRemove,
  onMove,
}: {
  section: TemplateSection
  onChange: (section: TemplateSection) => void
  onRemove: () => void
  onMove: (delta: number) => void
}) {
  const { t } = useTranslation()
  const [dragging, setDragging] = useState<number | null>(null)
  const [over, setOver] = useState<number | null>(null)
  const items = section.items ?? []
  const setItems = (next: TemplateItem[]) =>
    onChange({ ...section, items: next })

  return (
    <Card className='gap-3 py-4'>
      <CardHeader className='flex flex-row items-center gap-2 px-4'>
        <Input
          className='font-medium'
          aria-label={t('inspections.section_title')}
          value={section.title}
          onChange={(e) => onChange({ ...section, title: e.target.value })}
        />
        <Button
          size='icon'
          variant='ghost'
          aria-label={t('inspections.move_up')}
          onClick={() => onMove(-1)}
        >
          <ArrowUp />
        </Button>
        <Button
          size='icon'
          variant='ghost'
          aria-label={t('inspections.move_down')}
          onClick={() => onMove(1)}
        >
          <ArrowDown />
        </Button>
        <Button
          size='icon'
          variant='ghost'
          aria-label={t('inspections.remove_section')}
          onClick={onRemove}
        >
          <Trash2 />
        </Button>
      </CardHeader>
      <CardContent className='grid gap-2 px-4'>
        {items.map((item, i) => (
          <div
            key={i}
            className={cn(
              over === i && dragging !== i && 'border-t-2 border-primary'
            )}
          >
            <ItemEditor
              item={item}
              onChange={(next) =>
                setItems(items.map((it, j) => (j === i ? next : it)))
              }
              onRemove={() => setItems(items.filter((_, j) => j !== i))}
              onMove={(delta) => setItems(move(items, i, i + delta))}
              dragProps={{
                draggable: true,
                onDragStart: () => setDragging(i),
                onDragOver: (e) => {
                  e.preventDefault()
                  setOver(i)
                },
                onDragEnd: () => {
                  setDragging(null)
                  setOver(null)
                },
                onDrop: (e) => {
                  e.preventDefault()
                  if (dragging !== null) setItems(move(items, dragging, i))
                  setDragging(null)
                  setOver(null)
                },
              }}
            />
          </div>
        ))}
        <Button
          size='sm'
          variant='outline'
          className='w-fit'
          onClick={() => setItems([...items, blankItem()])}
        >
          <Plus /> {t('inspections.add_item')}
        </Button>
      </CardContent>
    </Card>
  )
}

function Editor({
  projectId,
  template,
  onSaved,
}: {
  projectId: number
  template: Template | null
  onSaved: (t: Template) => void
}) {
  const { t } = useTranslation()
  const save = useSaveTemplate(projectId)
  const [draft, setDraft] = useState<Draft>(() =>
    template
      ? {
          name: template.name,
          trade: template.trade ?? '',
          activity: template.activity ?? '',
          description: template.description ?? '',
          active: template.active,
          sections: template.sections,
          area: template.area as Draft['area'],
          is_formal: template.is_formal,
          audit_scope: template.audit_scope as Draft['audit_scope'],
          requires_client_signature: template.requires_client_signature,
          required_qualification: template.required_qualification,
          kind: 'inspection',
          linked_issue_types: template.linked_issue_types ?? [],
          activities: [],
        }
      : blank()
  )
  const sections = draft.sections ?? []
  const setSections = (next: TemplateSection[]) =>
    setDraft({ ...draft, sections: next })

  return (
    <form
      className='grid gap-4'
      onSubmit={(e) => {
        e.preventDefault()
        const cleaned = sections
          .map((s) => ({
            ...s,
            items: (s.items ?? []).filter((i) => i.text.trim()),
          }))
          .filter((s) => s.title.trim())
        save.mutate(
          {
            id: template?.id,
            body: {
              ...draft,
              trade: draft.trade || null,
              activity: draft.activity || null,
              description: draft.description || null,
              sections: cleaned,
              project_id: projectId,
            },
          },
          {
            onSuccess: (saved) => {
              toast.success(t('inspections.template_saved'))
              onSaved(saved as Template)
            },
          }
        )
      }}
    >
      <div className='grid gap-3 sm:grid-cols-2'>
        <div className='grid gap-1.5'>
          <Label htmlFor='tpl-name'>{t('inspections.template_name')}</Label>
          <Input
            id='tpl-name'
            required
            value={draft.name}
            onChange={(e) => setDraft({ ...draft, name: e.target.value })}
          />
        </div>
        <div className='grid gap-1.5'>
          <Label htmlFor='tpl-trade'>{t('inspections.trade')}</Label>
          <Input
            id='tpl-trade'
            placeholder='Insulation, Cladding, Refractory, Coatings'
            value={draft.trade ?? ''}
            onChange={(e) => setDraft({ ...draft, trade: e.target.value })}
          />
        </div>
        <div className='grid gap-1.5 sm:col-span-2'>
          <Label htmlFor='tpl-activity'>{t('inspections.activity')}</Label>
          <Input
            id='tpl-activity'
            value={draft.activity ?? ''}
            onChange={(e) => setDraft({ ...draft, activity: e.target.value })}
          />
        </div>
        <div className='grid gap-1.5 sm:col-span-2'>
          <Label htmlFor='tpl-description'>
            {t('inspections.template_description')}
          </Label>
          <Textarea
            id='tpl-description'
            value={draft.description ?? ''}
            onChange={(e) =>
              setDraft({ ...draft, description: e.target.value })
            }
          />
        </div>
      </div>
      <TemplateSettingsFields
        value={draft}
        onChange={(next) => setDraft({ ...draft, ...next })}
      />
      {sections.map((section, i) => (
        <SectionEditor
          key={i}
          section={section}
          onChange={(next) =>
            setSections(sections.map((s, j) => (j === i ? next : s)))
          }
          onRemove={() => setSections(sections.filter((_, j) => j !== i))}
          onMove={(delta) => setSections(move(sections, i, i + delta))}
        />
      ))}
      <div className='flex flex-wrap gap-2'>
        <Button
          type='button'
          variant='outline'
          onClick={() =>
            setSections([
              ...sections,
              { title: t('inspections.new_section'), items: [blankItem()] },
            ])
          }
        >
          <Plus /> {t('inspections.add_section')}
        </Button>
        <Button type='submit' className='ms-auto' disabled={save.isPending}>
          <Save /> {t('common.save')}
        </Button>
      </div>
    </form>
  )
}

function Templates({ projectId }: { projectId: number }) {
  const { t } = useTranslation()
  const session = useSession()
  const editable = can(session, 'inspections.update')
  const { data: templates = [] } = useTemplates(projectId)
  const action = useTemplateAction(projectId)
  const [selected, setSelected] = useState<number | 'new' | 'new-itp' | null>(
    null
  )
  const current =
    selected === 'new' || selected === 'new-itp'
      ? null
      : templates.find((tpl) => tpl.id === selected)
  const itp = selected === 'new-itp' || current?.kind === 'itp'

  return (
    <div className='grid gap-4 lg:grid-cols-[320px_1fr]'>
      <div className='grid content-start gap-2'>
        {editable ? (
          <div className='flex gap-2'>
            <Button size='sm' onClick={() => setSelected('new')}>
              <Plus /> {t('inspections.new_template')}
            </Button>
            <Button
              size='sm'
              variant='outline'
              onClick={() => setSelected('new-itp')}
            >
              <Plus /> {t('inspections.new_itp')}
            </Button>
            <Button
              size='sm'
              variant='outline'
              onClick={() => action.mutate({ action: 'starter' })}
            >
              <Sparkles /> {t('inspections.starters')}
            </Button>
          </div>
        ) : null}
        {templates.map((tpl) => (
          <button
            key={tpl.id}
            onClick={() => setSelected(tpl.id)}
            className={cn(
              'grid gap-0.5 rounded-md border px-3 py-2 text-start text-sm hover:bg-muted',
              selected === tpl.id && 'border-primary bg-muted'
            )}
          >
            <span className='font-medium'>{tpl.name}</span>
            <span className='text-xs text-muted-foreground'>
              {[
                tpl.kind === 'itp' ? 'ITP' : t(`inspections.areas.${tpl.area}`),
                tpl.is_formal ? t('inspections.formal_short') : null,
                tpl.trade,
                `v${tpl.version}`,
                `${tpl.item_count} ${t('inspections.items')}`,
              ]
                .filter(Boolean)
                .join(' · ')}
            </span>
          </button>
        ))}
      </div>
      <div>
        {selected === null ? (
          <p className='text-sm text-muted-foreground'>
            {t('inspections.pick_template')}
          </p>
        ) : !editable && current ? (
          <Card>
            <CardHeader>
              <CardTitle>{current.name}</CardTitle>
            </CardHeader>
            <CardContent className='grid gap-3'>
              {current.sections.map((s) => (
                <div key={s.title}>
                  <p className='font-medium'>{s.title}</p>
                  <ul className='list-disc ps-5 text-sm'>
                    {(s.items ?? []).map((i) => (
                      <li key={i.text}>{i.text}</li>
                    ))}
                  </ul>
                </div>
              ))}
              {(current.activities ?? []).length ? (
                <ol className='grid list-decimal gap-1 ps-5 text-sm'>
                  {(current.activities ?? []).map((a, i) => (
                    <li key={i}>
                      <span className='me-2'>{a.title}</span>
                      <PointBadges points={a.points ?? {}} />
                    </li>
                  ))}
                </ol>
              ) : null}
            </CardContent>
          </Card>
        ) : (
          <div className='grid gap-3'>
            {current ? (
              <div className='flex items-center gap-2'>
                <Badge variant='secondary'>v{current.version}</Badge>
                <Button
                  size='sm'
                  variant='outline'
                  className='ms-auto'
                  onClick={() =>
                    action.mutate(
                      { id: current.id, action: 'duplicate' },
                      {
                        onSuccess: (copy) => setSelected((copy as Template).id),
                      }
                    )
                  }
                >
                  <Copy /> {t('inspections.duplicate')}
                </Button>
                {can(session, 'inspections.delete') ? (
                  <Button
                    size='sm'
                    variant='outline'
                    onClick={() =>
                      action.mutate(
                        { id: current.id, action: 'delete' },
                        { onSuccess: () => setSelected(null) }
                      )
                    }
                  >
                    <Trash2 /> {t('inspections.delete')}
                  </Button>
                ) : null}
              </div>
            ) : null}
            {itp ? (
              <ItpEditor
                key={`${selected}-${current?.version ?? 0}`}
                projectId={projectId}
                template={current ?? null}
                onSaved={(saved) => setSelected(saved.id)}
              />
            ) : (
              <Editor
                key={`${selected}-${current?.version ?? 0}`}
                projectId={projectId}
                template={current ?? null}
                onSaved={(saved) => setSelected(saved.id)}
              />
            )}
          </div>
        )}
      </div>
    </div>
  )
}

export default function TemplatesPage() {
  const { t } = useTranslation()
  const project = useCurrentProject()
  return (
    <Page
      title={t('inspections.templates')}
      description={t('inspections.templates_description')}
      projectScoped
      actions={
        <Button size='sm' variant='ghost' asChild>
          <Link to='/$' params={{ _splat: 'inspections' }}>
            <ArrowLeft /> {t('inspections.register')}
          </Link>
        </Button>
      }
    >
      {project ? (
        <Templates key={project.id} projectId={project.id} />
      ) : (
        <p className='text-sm text-muted-foreground'>
          {t('inspections.no_project')}
        </p>
      )}
    </Page>
  )
}
