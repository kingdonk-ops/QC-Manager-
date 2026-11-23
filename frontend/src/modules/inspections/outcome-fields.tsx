import { useTranslation } from 'react-i18next'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { NativeSelect } from '@/components/native-select'
import { type OutcomeState, SEVERITIES, effectiveSeverity } from './outcome-state'

/**
 * Conditional acceptance (pass only), the measured value and the severity of the report an outcome raises.
 * The client never decides pass or fail from a criterion; the server judges.
 */
export function OutcomeFields({
  result,
  value,
  onChange,
  idPrefix = 'outcome',
}: {
  result: 'pass' | 'fail'
  value: OutcomeState
  onChange: (next: OutcomeState) => void
  idPrefix?: string
}) {
  const { t } = useTranslation()
  const conditional = result === 'pass' && value.conditional
  const withSeverity = result === 'fail' || conditional
  return (
    <div className='grid gap-3 rounded-md border p-3'>
      {result === 'pass' ? (
        <label className='flex items-start gap-2 text-sm'>
          <Checkbox
            data-testid='outcome-conditional'
            checked={value.conditional}
            onCheckedChange={(v) =>
              onChange({ ...value, conditional: v === true })
            }
            className='mt-0.5'
          />
          {t('inspections.criterion.conditional_label')}
        </label>
      ) : null}
      <div className='grid gap-3 sm:grid-cols-2'>
        <div className='grid gap-1.5'>
          <Label htmlFor={`${idPrefix}-measured`}>
            {t('inspections.criterion.measured_value')}
          </Label>
          <Input
            id={`${idPrefix}-measured`}
            maxLength={40}
            inputMode='decimal'
            placeholder={t('inspections.criterion.measured_hint')}
            value={value.measured}
            onChange={(e) => onChange({ ...value, measured: e.target.value })}
          />
        </div>
        {withSeverity ? (
          <div className='grid gap-1.5'>
            <Label htmlFor={`${idPrefix}-severity`}>
              {t('inspections.criterion.report_severity')}
            </Label>
            <NativeSelect
              id={`${idPrefix}-severity`}
              options={SEVERITIES.map((s) => ({
                value: s,
                label: t(`inspections.criterion.severity.${s}`),
              }))}
              value={effectiveSeverity(result, value)}
              onChange={(e) => onChange({ ...value, severity: e.target.value })}
            />
          </div>
        ) : null}
      </div>
    </div>
  )
}
