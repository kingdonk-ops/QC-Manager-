import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { money } from '@/lib/format'
import { Input } from '@/components/ui/input'
import { Field } from '@/components/records/fields'
import { useHire } from './api'

export function HireView({
  projectId,
  currency,
}: {
  projectId: number
  currency: string
}) {
  const { t } = useTranslation()
  const [start, setStart] = useState('')
  const { data } = useHire(projectId, start)
  const fmt = money(currency)
  return (
    <div className='grid gap-3'>
      <div className='flex items-end gap-2'>
        <Field label={t('scaffolds.period_from')}>
          <Input
            type='date'
            className='h-8 w-44'
            value={start}
            onChange={(e) => setStart(e.target.value)}
          />
        </Field>
        <p className='pb-1 text-sm text-muted-foreground'>
          {t('scaffolds.hire_help')}
        </p>
      </div>
      <table className='w-full text-sm'>
        <thead className='text-left text-muted-foreground'>
          <tr>
            <th>{t('scaffolds.code')}</th>
            <th>{t('scaffolds.location')}</th>
            <th>{t('scaffolds.erected')}</th>
            <th className='text-right'>{t('scaffolds.days')}</th>
            <th className='text-right'>{t('scaffolds.hire_rate')}</th>
            <th className='text-right'>{t('scaffolds.hire_cost')}</th>
          </tr>
        </thead>
        <tbody>
          {(data?.lines ?? []).map((l) => (
            <tr key={l.scaffold_id} className='border-t'>
              <td>{l.code}</td>
              <td>{l.node_path}</td>
              <td>
                {l.erected_on}
                {l.dismantled_on ? ` → ${l.dismantled_on}` : ''}
              </td>
              <td className='text-right'>{l.days}</td>
              <td className='text-right'>
                {l.rate != null ? fmt({ value: l.rate }) : '—'}
              </td>
              <td className='text-right'>
                {l.cost != null ? fmt({ value: l.cost }) : '—'}
              </td>
            </tr>
          ))}
          <tr className='border-t font-semibold'>
            <td colSpan={3}>{t('scaffolds.total')}</td>
            <td className='text-right'>{data?.total_days ?? 0}</td>
            <td />
            <td className='text-right'>
              {fmt({ value: data?.total_cost ?? 0 })}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  )
}
