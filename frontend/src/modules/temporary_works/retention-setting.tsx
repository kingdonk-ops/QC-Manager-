import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { useRetention, useSetRetention } from './api'

/** The recycle bin's retention in whole days: one input and a save, within the range the server reports. */
export function RetentionForm({
  days,
  min,
  max,
  defaultDays,
  pending,
  onSave,
}: {
  days: number
  min: number
  max: number
  defaultDays: number
  pending?: boolean
  onSave: (days: number) => void
}) {
  const { t } = useTranslation()
  const [value, setValue] = useState(String(days))
  const n = Number(value)
  const valid = Number.isInteger(n) && n >= min && n <= max
  return (
    <form
      className='flex flex-wrap items-end gap-2'
      data-testid='retention-form'
      onSubmit={(e) => {
        e.preventDefault()
        if (valid) onSave(n)
      }}
    >
      <label className='grid gap-1 text-sm'>
        {t('temporary_works.retention.label')}
        <span className='flex items-center gap-2'>
          <Input
            type='number'
            min={min}
            max={max}
            className='h-8 w-24'
            data-testid='retention-input'
            aria-invalid={valid ? undefined : true}
            value={value}
            onChange={(e) => setValue(e.target.value)}
          />
          {t('temporary_works.retention.days')}
        </span>
      </label>
      <Button
        type='submit'
        size='sm'
        data-testid='retention-save'
        disabled={!valid || pending || n === days}
      >
        {t('temporary_works.retention.save')}
      </Button>
      <p className='basis-full text-xs text-muted-foreground'>
        {t('temporary_works.retention.help', {
          max,
          default: defaultDays,
        })}
      </p>
    </form>
  )
}

/** The project's retention setting, loaded and saved through the server. */
export function RetentionSetting({ projectId }: { projectId: number }) {
  const { t } = useTranslation()
  const { data } = useRetention(projectId)
  const save = useSetRetention()
  if (!data) return null
  return (
    <RetentionForm
      key={data.bin_retention_days}
      days={data.bin_retention_days}
      min={data.min_days ?? 1}
      max={data.max_days ?? 60}
      defaultDays={data.default_days ?? 30}
      pending={save.isPending}
      onSave={(days) =>
        save.mutate(
          { project_id: projectId, bin_retention_days: days },
          { onSuccess: () => toast.success(t('temporary_works.retention.saved')) }
        )
      }
    />
  )
}
