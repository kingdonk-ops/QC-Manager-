import { useTranslation } from 'react-i18next'
import { Kpi } from '@/components/records/fields'
import { formatClearance } from './rules'

/**
 * Four figures from the server rollup: items, design clearance (a dash when absent), items bearing load (loaded plus
 * in use) and breaches, which take the error tone above zero.
 */
export function HeadlineFigures({
  total,
  clearance,
  bearingLoad,
  breaches,
}: {
  total: number
  clearance: string | null | undefined
  bearingLoad: number
  breaches: number
}) {
  const { t } = useTranslation()
  return (
    <div className='grid grid-cols-2 gap-3 md:grid-cols-4'>
      <div data-testid='figure-items'>
        <Kpi label={t('temporary_works.figure.items')} value={total} />
      </div>
      <div data-testid='figure-clearance'>
        <Kpi
          label={t('temporary_works.figure.clearance')}
          value={formatClearance(clearance)}
        />
      </div>
      <div data-testid='figure-bearing-load'>
        <Kpi
          label={t('temporary_works.figure.bearing_load')}
          value={bearingLoad}
        />
      </div>
      <div
        data-testid='figure-breaches'
        data-tone={breaches > 0 ? 'bad' : 'none'}
      >
        <Kpi
          label={t('temporary_works.figure.breaches')}
          value={breaches}
          tone={breaches > 0 ? 'bad' : undefined}
        />
      </div>
    </div>
  )
}
