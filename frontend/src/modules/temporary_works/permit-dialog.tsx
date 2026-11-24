import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  useCreatePermit,
  useUpdatePermit,
  type Finding,
  type Item,
  type Permit,
} from './api'
import { AreaControl, SelectControl, TextControl } from './form-controls'
import {
  permitCreateBody,
  permitDraft,
  permitUpdateBody,
  validatePermit,
  type PermitDraft,
} from './form-schemas'
import { PERMIT_KINDS, kindKey } from './rules'
import { WarningsList } from './warnings-list'

type FormProps = {
  initial: PermitDraft
  pending?: boolean
  submitLabel: string
  onSubmit: (draft: PermitDraft) => void
}

/** The permit form. The two prerequisite flags appear only for a permit to load; the other kinds ignore them. */
export function PermitForm({
  initial,
  pending,
  submitLabel,
  onSubmit,
}: FormProps) {
  const { t } = useTranslation()
  const [d, setD] = useState(initial)
  const [touched, setTouched] = useState<Set<string>>(new Set())
  const errors = validatePermit(d)
  const touch = (field: string) => setTouched(new Set(touched).add(field))
  const shown = (field: string) =>
    touched.has(field) ? errors[field] : undefined
  const set = (patch: Partial<PermitDraft>) => setD({ ...d, ...patch })
  return (
    <form
      id='tw-permit-form'
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
        id='tw-permit-number'
        label={t('temporary_works.permit.number')}
        value={d.number}
        onChange={(number) => set({ number })}
        onBlur={() => touch('number')}
        error={shown('number')}
      />
      <SelectControl
        id='tw-permit-kind'
        label={t('temporary_works.permit.kind')}
        options={PERMIT_KINDS.map((k) => ({ value: k, label: t(kindKey(k)) }))}
        value={d.kind}
        onChange={(kind) => set({ kind })}
        onBlur={() => touch('kind')}
        error={shown('kind')}
      />
      <TextControl
        id='tw-permit-issued-by'
        label={t('temporary_works.permit.issued_by')}
        value={d.issued_by_name}
        onChange={(issued_by_name) => set({ issued_by_name })}
        className='sm:col-span-2'
      />
      <TextControl
        id='tw-permit-from'
        type='date'
        label={t('temporary_works.permit.valid_from')}
        value={d.valid_from}
        onChange={(valid_from) => set({ valid_from })}
        onBlur={() => touch('valid_to')}
      />
      <TextControl
        id='tw-permit-to'
        type='date'
        label={t('temporary_works.permit.valid_to')}
        value={d.valid_to}
        onChange={(valid_to) => set({ valid_to })}
        onBlur={() => touch('valid_to')}
        error={shown('valid_to')}
      />
      {d.kind === 'load' ? (
        <fieldset
          data-testid='tw-prerequisites'
          className='grid gap-2 rounded-md border p-3 sm:col-span-2'
        >
          <legend className='px-1 text-sm font-medium'>
            {t('temporary_works.permit.prerequisites')}
          </legend>
          <label className='flex items-center gap-2 text-sm'>
            <Checkbox
              checked={d.design_check_accepted}
              onCheckedChange={(v) =>
                set({ design_check_accepted: v === true })
              }
            />
            {t('temporary_works.design_check_accepted')}
          </label>
          <label className='flex items-center gap-2 text-sm'>
            <Checkbox
              checked={d.inspection_passed}
              onCheckedChange={(v) => set({ inspection_passed: v === true })}
            />
            {t('temporary_works.inspection_passed')}
          </label>
        </fieldset>
      ) : null}
      <AreaControl
        id='tw-permit-conditions'
        label={t('temporary_works.permit.conditions')}
        value={d.conditions}
        onChange={(conditions) => set({ conditions })}
        className='sm:col-span-2'
      />
      <div className='flex justify-end sm:col-span-2'>
        <Button type='submit' data-testid='tw-permit-submit' disabled={pending}>
          {submitLabel}
        </Button>
      </div>
    </form>
  )
}

/** Create a draft permit for an item, or edit a draft one. Warnings that come back are listed and never block. */
export function PermitDialog({
  item,
  permit,
  onClose,
}: {
  item: Item
  permit?: Permit
  onClose: () => void
}) {
  const { t } = useTranslation()
  const create = useCreatePermit(item.id)
  const update = useUpdatePermit(permit?.id ?? 0)
  const [warnings, setWarnings] = useState<Finding[] | null>(null)
  const done = (written: { warnings?: Finding[] }) => {
    if (written.warnings && written.warnings.length > 0)
      setWarnings(written.warnings)
    else onClose()
  }
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className='max-h-[90vh] overflow-y-auto sm:max-w-xl'>
        <DialogHeader>
          <DialogTitle>
            {permit
              ? t('temporary_works.permit.edit_title', {
                  number: permit.number,
                })
              : t('temporary_works.permit.new_title', {
                  reference: item.reference,
                })}
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
          <PermitForm
            initial={permitDraft(permit)}
            pending={create.isPending || update.isPending}
            submitLabel={
              permit ? t('temporary_works.save') : t('temporary_works.permit.add')
            }
            onSubmit={(draft) => {
              if (!permit) {
                create.mutate(permitCreateBody(draft), { onSuccess: done })
                return
              }
              const body = permitUpdateBody(permit, draft)
              if (Object.keys(body).length === 0) onClose()
              else update.mutate(body, { onSuccess: done })
            }}
          />
        )}
      </DialogContent>
    </Dialog>
  )
}
