import { useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { UserSelect, type Option } from '@/components/native-select'
import {
  useCreateItem,
  useScaffoldPicker,
  useUpdateItem,
  type Finding,
  type Item,
} from './api'
import {
  AreaControl,
  Control,
  SelectControl,
  TextControl,
} from './form-controls'
import {
  itemCreateBody,
  itemDraft,
  itemUpdateBody,
  validateItem,
  type ItemDraft,
} from './form-schemas'
import { CATEGORIES, FAMILIES, categoryKey, familyKey } from './rules'
import { WarningsList } from './warnings-list'

type FormProps = {
  initial: ItemDraft
  scaffolds: Option[]
  /** The coordinator user picker; the dialog supplies the people list, tests supply a stand-in. */
  coordinatorControl?: (
    value: number | null,
    onChange: (id: number | null) => void
  ) => ReactNode
  pending?: boolean
  submitLabel: string
  onSubmit: (draft: ItemDraft) => void
}

/**
 * The item form. Messages show once a field has been touched; the buttons stay enabled so a first press touches every
 * field and shows what is missing.
 */
export function ItemForm({
  initial,
  scaffolds,
  coordinatorControl,
  pending,
  submitLabel,
  onSubmit,
}: FormProps) {
  const { t } = useTranslation()
  const [d, setD] = useState(initial)
  const [touched, setTouched] = useState<Set<string>>(new Set())
  const errors = validateItem(d)
  const touch = (field: string) => setTouched(new Set(touched).add(field))
  const shown = (field: string) =>
    touched.has(field) ? errors[field] : undefined
  const set = (patch: Partial<ItemDraft>) => setD({ ...d, ...patch })
  const setRelated = (i: number, patch: Partial<ItemDraft['related'][0]>) =>
    set({ related: d.related.map((r, j) => (j === i ? { ...r, ...patch } : r)) })

  return (
    <form
      id='tw-item-form'
      className='grid gap-3 sm:grid-cols-2'
      noValidate
      onSubmit={(e) => {
        e.preventDefault()
        if (Object.keys(errors).length > 0) {
          setTouched(new Set(Object.keys(errors)))
          return
        }
        onSubmit(d)
      }}
    >
      <TextControl
        id='tw-reference'
        label={t('temporary_works.item.reference')}
        value={d.reference}
        onChange={(reference) => set({ reference })}
        onBlur={() => touch('reference')}
        error={shown('reference')}
      />
      <SelectControl
        id='tw-family'
        label={t('temporary_works.item.family')}
        placeholder={t('temporary_works.item.family_placeholder')}
        options={FAMILIES.map((f) => ({ value: f, label: t(familyKey(f)) }))}
        value={d.family}
        onChange={(family) =>
          set({
            family,
            scaffold_id: family === 'scaffold' ? d.scaffold_id : null,
          })
        }
        onBlur={() => touch('family')}
        error={shown('family')}
      />
      <TextControl
        id='tw-title'
        label={t('temporary_works.item.title')}
        value={d.title}
        onChange={(title) => set({ title })}
        onBlur={() => touch('title')}
        error={shown('title')}
        className='sm:col-span-2'
      />
      <SelectControl
        id='tw-category'
        label={t('temporary_works.item.category')}
        placeholder={t('temporary_works.category_unassigned')}
        options={CATEGORIES.map((c) => ({
          value: String(c),
          label: t(categoryKey(c)),
        }))}
        value={d.category}
        onChange={(category) => set({ category })}
      />
      <TextControl
        id='tw-sort'
        label={t('temporary_works.item.sort_order')}
        type='number'
        value={d.sort_order}
        onChange={(sort_order) => set({ sort_order })}
        onBlur={() => touch('sort_order')}
        error={shown('sort_order')}
      />
      <TextControl
        id='tw-designer'
        label={t('temporary_works.item.designer')}
        value={d.designer}
        onChange={(designer) => set({ designer })}
      />
      <TextControl
        id='tw-checker'
        label={t('temporary_works.item.checker')}
        value={d.checker}
        onChange={(checker) => set({ checker })}
      />
      <TextControl
        id='tw-coordinator'
        label={t('temporary_works.item.coordinator_name')}
        value={d.coordinator_name}
        onChange={(coordinator_name) => set({ coordinator_name })}
      />
      {coordinatorControl ? (
        <Control
          id='tw-coordinator-user'
          label={t('temporary_works.item.coordinator_user')}
        >
          {coordinatorControl(d.coordinator_user_id, (coordinator_user_id) =>
            set({ coordinator_user_id })
          )}
        </Control>
      ) : null}
      <TextControl
        id='tw-design-due'
        type='date'
        label={t('temporary_works.design_due')}
        value={d.design_due_on}
        onChange={(design_due_on) => set({ design_due_on })}
      />
      <TextControl
        id='tw-required-load'
        type='date'
        label={t('temporary_works.required_load')}
        value={d.required_load_on}
        onChange={(required_load_on) => set({ required_load_on })}
        onBlur={() => touch('required_strike_on')}
      />
      <TextControl
        id='tw-required-strike'
        type='date'
        label={t('temporary_works.required_strike')}
        value={d.required_strike_on}
        onChange={(required_strike_on) => set({ required_strike_on })}
        onBlur={() => touch('required_strike_on')}
        error={shown('required_strike_on')}
      />
      <TextControl
        id='tw-location'
        label={t('temporary_works.item.location')}
        value={d.location}
        onChange={(location) => set({ location })}
      />
      {d.family === 'scaffold' ? (
        <SelectControl
          id='tw-scaffold'
          label={t('temporary_works.item.scaffold')}
          placeholder={t('temporary_works.item.scaffold_none')}
          options={scaffolds}
          value={d.scaffold_id ? String(d.scaffold_id) : ''}
          onChange={(v) => set({ scaffold_id: v ? Number(v) : null })}
        />
      ) : null}
      <AreaControl
        id='tw-description'
        label={t('temporary_works.item.description')}
        value={d.description}
        onChange={(description) => set({ description })}
        className='sm:col-span-2'
      />
      <AreaControl
        id='tw-notes'
        label={t('temporary_works.item.notes')}
        value={d.notes}
        onChange={(notes) => set({ notes })}
        className='sm:col-span-2'
      />
      <div className='grid gap-2 sm:col-span-2'>
        <p className='text-sm font-medium'>
          {t('temporary_works.item.related')}
        </p>
        {d.related.map((r, i) => (
          <div key={i} className='flex gap-2'>
            <Input
              aria-label={t('temporary_works.item.related_key')}
              placeholder={t('temporary_works.item.related_key')}
              value={r.key}
              onChange={(e) => setRelated(i, { key: e.target.value })}
            />
            <Input
              aria-label={t('temporary_works.item.related_value')}
              placeholder={t('temporary_works.item.related_value')}
              value={r.value}
              onChange={(e) => setRelated(i, { value: e.target.value })}
            />
            <Button
              type='button'
              variant='outline'
              size='sm'
              onClick={() =>
                set({ related: d.related.filter((_, j) => j !== i) })
              }
            >
              {t('temporary_works.item.related_remove')}
            </Button>
          </div>
        ))}
        <Button
          type='button'
          variant='outline'
          size='sm'
          className='justify-self-start'
          onClick={() =>
            set({ related: [...d.related, { key: '', value: '' }] })
          }
        >
          {t('temporary_works.item.related_add')}
        </Button>
      </div>
      <div className='flex justify-end sm:col-span-2'>
        <Button type='submit' data-testid='tw-item-submit' disabled={pending}>
          {submitLabel}
        </Button>
      </div>
    </form>
  )
}

/**
 * Create or edit an item. After a save that returns warnings they are listed (they never block); otherwise the dialog
 * closes. `preset` fills the family and scaffold link, for the shortcut on a scaffold's record.
 */
export function ItemDialog({
  projectId,
  item,
  preset,
  onClose,
}: {
  projectId: number
  item?: Item
  preset?: { family?: string; scaffold_id?: number }
  onClose: () => void
}) {
  const { t } = useTranslation()
  const create = useCreateItem()
  const update = useUpdateItem(item?.id ?? 0)
  const { data: scaffolds = [] } = useScaffoldPicker(projectId, true)
  const [warnings, setWarnings] = useState<Finding[] | null>(null)
  const done = (written: { warnings?: Finding[] }) => {
    if (written.warnings && written.warnings.length > 0)
      setWarnings(written.warnings)
    else onClose()
  }
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className='max-h-[90vh] overflow-y-auto sm:max-w-2xl'>
        <DialogHeader>
          <DialogTitle>
            {item
              ? t('temporary_works.item.edit_title', {
                  reference: item.reference,
                })
              : t('temporary_works.item.new_title')}
          </DialogTitle>
        </DialogHeader>
        {warnings ? (
          <>
            <WarningsList warnings={warnings} />
            <DialogFooter>
              <Button onClick={onClose}>{t('temporary_works.done')}</Button>
            </DialogFooter>
          </>
        ) : (
          <ItemForm
            initial={itemDraft(item, preset)}
            scaffolds={scaffolds.map((s) => ({
              value: String(s.id),
              label: s.code,
            }))}
            coordinatorControl={(value, onChange) => (
              <UserSelect value={value} onChange={onChange} />
            )}
            pending={create.isPending || update.isPending}
            submitLabel={
              item ? t('temporary_works.save') : t('temporary_works.create')
            }
            onSubmit={(draft) => {
              if (!item) {
                create.mutate(itemCreateBody(projectId, draft), {
                  onSuccess: done,
                })
                return
              }
              const body = itemUpdateBody(item, draft)
              if (Object.keys(body).length === 0) onClose()
              else update.mutate(body, { onSuccess: done })
            }}
          />
        )}
      </DialogContent>
    </Dialog>
  )
}
