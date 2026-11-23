import { useTranslation } from 'react-i18next'
import { Input } from '@/components/ui/input'
import { NativeSelect } from '@/components/native-select'
import type { TemplateItem } from './api'
import { type Criterion, useCriteria } from './criteria-api'
import { criterionLabel } from './criterion-label'

/** The list of criteria as a select; a criterion that is no longer offered stays visible by its number. */
export function CriterionSelect({
  criteria,
  value,
  onChange,
  disabled,
  id,
  className,
}: {
  criteria: Criterion[]
  value: number | null | undefined
  onChange: (criterion: Criterion | null) => void
  disabled?: boolean
  id?: string
  className?: string
}) {
  const { t } = useTranslation()
  const options = criteria.map((c) => ({
    value: String(c.id),
    label: criterionLabel(c),
  }))
  if (value && !criteria.some((c) => c.id === value))
    options.push({ value: String(value), label: `#${value}` })
  return (
    <NativeSelect
      id={id}
      className={className}
      disabled={disabled}
      aria-label={t('inspections.criteria.picker')}
      placeholder={t('inspections.criteria.picker_none')}
      options={options}
      value={value ? String(value) : ''}
      onChange={(e) =>
        onChange(criteria.find((c) => String(c.id) === e.target.value) ?? null)
      }
    />
  )
}

/** The project's active criteria (plus the one already chosen) as a picker. */
export function CriterionPicker({
  projectId,
  value,
  onChange,
  disabled,
  id,
  className,
}: {
  projectId: number
  value: number | null | undefined
  onChange: (criterion: Criterion | null) => void
  disabled?: boolean
  id?: string
  className?: string
}) {
  const { data = [] } = useCriteria(projectId)
  return (
    <CriterionSelect
      id={id}
      className={className}
      disabled={disabled}
      criteria={data.filter((c) => c.active || c.id === value)}
      value={value}
      onChange={onChange}
    />
  )
}

const num = (v: string) => (v.trim() === '' ? null : Number(v))

/** Unit, minimum and maximum of a numeric item; read-only while a criterion supplies them. */
export function ItemLimits({
  item,
  onChange,
}: {
  item: TemplateItem
  onChange: (item: TemplateItem) => void
}) {
  const { t } = useTranslation()
  const locked = item.criterion_id != null
  return (
    <>
      <Input
        className='h-8 w-20'
        placeholder={t('inspections.unit')}
        aria-label={t('inspections.unit')}
        readOnly={locked}
        value={item.unit ?? ''}
        onChange={(e) => onChange({ ...item, unit: e.target.value || null })}
      />
      <Input
        className='h-8 w-24'
        type='number'
        step='any'
        placeholder={t('inspections.min')}
        aria-label={t('inspections.min')}
        readOnly={locked}
        value={item.min_value ?? ''}
        onChange={(e) => onChange({ ...item, min_value: num(e.target.value) })}
      />
      <Input
        className='h-8 w-24'
        type='number'
        step='any'
        placeholder={t('inspections.max')}
        aria-label={t('inspections.max')}
        readOnly={locked}
        value={item.max_value ?? ''}
        onChange={(e) => onChange({ ...item, max_value: num(e.target.value) })}
      />
      {locked ? (
        <span className='text-xs text-muted-foreground'>
          {t('inspections.criteria.picker_locked')}
        </span>
      ) : null}
    </>
  )
}
