import { useState } from 'react'
import {
  ArrowDown,
  ArrowUp,
  GripVertical,
  Plus,
  Save,
  Trash2,
} from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { NativeSelect } from '@/components/native-select'
import {
  type Template,
  type TemplateBody,
  type TemplateItem,
  type TemplateSection,
  useSaveTemplate,
} from './api'
import { useCriteria } from './criteria-api'
import { applyCriterion, presentItem } from './criterion-label'
import { CriterionPicker, ItemLimits } from './criterion-picker'
import { TemplateSettingsFields } from './template-settings'

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

function ItemEditor({
  projectId,
  item,
  onChange,
  onRemove,
  onMove,
  dragProps,
}: {
  projectId: number
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
        <CriterionPicker
          projectId={projectId}
          className='h-8 w-64'
          value={item.criterion_id}
          onChange={(c) => onChange(applyCriterion(item, c))}
        />
        {numeric ? <ItemLimits item={item} onChange={onChange} /> : null}
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
  projectId,
  section,
  onChange,
  onRemove,
  onMove,
}: {
  projectId: number
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
              projectId={projectId}
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

/** The checklist template editor: head fields, settings, then sections of items (numeric ones can pick a criterion). */
export function ChecklistEditor({
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
  const { data: criteria = [] } = useCriteria(projectId)
  // Items linked to a numeric criterion show (and save) as numeric readings with the criterion's limits.
  const sections = (draft.sections ?? []).map((s) => ({
    ...s,
    items: (s.items ?? []).map((i) => presentItem(i, criteria)),
  }))
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
          projectId={projectId}
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
