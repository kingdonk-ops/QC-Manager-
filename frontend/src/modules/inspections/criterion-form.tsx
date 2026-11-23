import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { NativeSelect } from '@/components/native-select'
import type { Criterion, CriterionFields } from './criteria-api'
import { type CriterionDraft, draftOf, fieldsOf } from './criterion-draft'
import {
  RULE_TYPES,
  deviationLimits,
  isNumericRule,
  nonNumericWarning,
  rangeOrderError,
} from './tolerance'

function Text({
  id,
  label,
  value,
  onChange,
  className,
  required,
}: {
  id: string
  label: string
  value: string
  onChange: (v: string) => void
  className?: string
  required?: boolean
}) {
  return (
    <div className={`grid gap-1.5 ${className ?? ''}`}>
      <Label htmlFor={id}>{label}</Label>
      <Input
        id={id}
        required={required}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
    </div>
  )
}

/**
 * The criterion form. Pre-validation mirrors only the range-order rule; the server's refusals (a frozen limit,
 * a duplicate code) arrive as `serverError` and are shown verbatim while the typed input stays.
 */
export function CriterionForm({
  initial,
  pending,
  serverError,
  onSubmit,
}: {
  initial?: Criterion | null
  pending?: boolean
  serverError?: string | null
  onSubmit: (fields: CriterionFields) => void
}) {
  const { t } = useTranslation()
  const [d, setD] = useState<CriterionDraft>(() => draftOf(initial))
  const [minus, setMinus] = useState('')
  const [plus, setPlus] = useState('')
  const set = (patch: Partial<CriterionDraft>) => setD({ ...d, ...patch })
  const swap = rangeOrderError(d.rule_type, d.lower_limit, d.upper_limit)
  const warn = nonNumericWarning(d.rule_type, d.lower_limit, d.upper_limit)
  const numeric = isNumericRule(d.rule_type)
  const computed = deviationLimits(d.nominal, minus, plus)

  return (
    <form
      className='grid gap-3'
      onSubmit={(e) => {
        e.preventDefault()
        if (!swap) onSubmit(fieldsOf(d))
      }}
    >
      <div className='grid gap-3 sm:grid-cols-3'>
        <Text
          id='crit-code'
          label={t('inspections.criteria.code')}
          value={d.code}
          required
          onChange={(code) => set({ code })}
        />
        <Text
          id='crit-title'
          label={t('inspections.criteria.title')}
          value={d.title}
          required
          className='sm:col-span-2'
          onChange={(title) => set({ title })}
        />
        <Text
          id='crit-standards'
          label={t('inspections.criteria.standards_ref')}
          value={d.standards_ref}
          onChange={(standards_ref) => set({ standards_ref })}
        />
        <Text
          id='crit-category'
          label={t('inspections.criteria.category')}
          value={d.category}
          onChange={(category) => set({ category })}
        />
        <Text
          id='crit-discipline'
          label={t('inspections.criteria.discipline')}
          value={d.discipline}
          onChange={(discipline) => set({ discipline })}
        />
        <Text
          id='crit-characteristic'
          label={t('inspections.criteria.characteristic')}
          value={d.characteristic}
          onChange={(characteristic) => set({ characteristic })}
        />
        <Text
          id='crit-method'
          label={t('inspections.criteria.method')}
          value={d.method}
          onChange={(method) => set({ method })}
        />
        <Text
          id='crit-unit'
          label={t('inspections.criteria.unit')}
          value={d.unit}
          onChange={(unit) => set({ unit })}
        />
      </div>
      <div className='grid gap-1.5'>
        <Label htmlFor='crit-details'>{t('inspections.criteria.details')}</Label>
        <Textarea
          id='crit-details'
          value={d.description}
          onChange={(e) => set({ description: e.target.value })}
        />
      </div>
      <div className='grid gap-3 sm:grid-cols-4'>
        <div className='grid gap-1.5'>
          <Label htmlFor='crit-rule'>{t('inspections.criteria.rule_type')}</Label>
          <NativeSelect
            id='crit-rule'
            options={RULE_TYPES.map((r) => ({
              value: r,
              label: t(`inspections.criteria.rule.${r}`),
            }))}
            value={d.rule_type}
            onChange={(e) =>
              set({ rule_type: e.target.value as CriterionDraft['rule_type'] })
            }
          />
        </div>
        <Text
          id='crit-nominal'
          label={t('inspections.criteria.nominal')}
          value={d.nominal}
          onChange={(nominal) => set({ nominal })}
        />
        <Text
          id='crit-lower'
          label={t('inspections.criteria.lower')}
          value={d.lower_limit}
          onChange={(lower_limit) => set({ lower_limit })}
        />
        <Text
          id='crit-upper'
          label={t('inspections.criteria.upper')}
          value={d.upper_limit}
          onChange={(upper_limit) => set({ upper_limit })}
        />
      </div>
      {swap ? (
        <p role='alert' data-testid='criterion-swap' className='text-sm text-red-600'>
          {t('inspections.criteria.swap')}
        </p>
      ) : null}
      {warn ? (
        <p data-testid='criterion-warning' className='text-sm text-amber-600'>
          {t('inspections.criteria.not_assessed_warning')}
        </p>
      ) : null}
      {numeric ? (
        <div className='grid gap-2 rounded-md border p-3'>
          <p className='text-sm font-medium'>
            {t('inspections.criteria.helper')}
          </p>
          <p className='text-xs text-muted-foreground'>
            {t('inspections.criteria.helper_help')}
          </p>
          <div className='flex flex-wrap items-end gap-2'>
            <div className='grid gap-1.5'>
              <Label htmlFor='crit-minus'>
                {t('inspections.criteria.minus')}
              </Label>
              <Input
                id='crit-minus'
                className='w-28'
                value={minus}
                onChange={(e) => setMinus(e.target.value)}
              />
            </div>
            <div className='grid gap-1.5'>
              <Label htmlFor='crit-plus'>{t('inspections.criteria.plus')}</Label>
              <Input
                id='crit-plus'
                className='w-28'
                value={plus}
                onChange={(e) => setPlus(e.target.value)}
              />
            </div>
            <Button
              type='button'
              variant='outline'
              disabled={!computed}
              data-testid='criterion-fill'
              onClick={() =>
                computed &&
                set({
                  lower_limit: computed.lower,
                  upper_limit: computed.upper,
                })
              }
            >
              {t('inspections.criteria.fill_limits')}
            </Button>
          </div>
        </div>
      ) : null}
      <label className='flex items-center gap-2 text-sm'>
        <Checkbox
          checked={d.active}
          onCheckedChange={(v) => set({ active: v === true })}
        />
        {t('inspections.criteria.active')}
      </label>
      {serverError ? (
        <p role='alert' data-testid='criterion-server-error' className='text-sm text-red-600'>
          {serverError}
        </p>
      ) : null}
      <div className='flex justify-end'>
        <Button
          type='submit'
          disabled={pending || !!swap || !d.code.trim() || !d.title.trim()}
        >
          {t('inspections.criteria.save')}
        </Button>
      </div>
    </form>
  )
}
