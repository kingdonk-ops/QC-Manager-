import { ShieldAlert, ShieldCheck } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import type { Breach } from './api'

/**
 * Leads the page. A breach banner lists each item bearing load without a valid permit to load, with its reason; when
 * there is none, a reassurance banner says so. A quieter banner shows the overdue counts only when above zero. All of
 * it is displayed from the server's rollup; nothing is worked out here.
 */
export function SafetyBanners({
  breaches,
  overdueToLoad,
  overdueToStrike,
}: {
  breaches: Breach[]
  overdueToLoad: number
  overdueToStrike: number
}) {
  const { t } = useTranslation()
  return (
    <div className='grid gap-2'>
      {breaches.length > 0 ? (
        <section
          role='alert'
          data-testid='breach-banner'
          data-count={breaches.length}
          className='rounded-md border border-red-600/50 bg-red-600/10 p-4'
        >
          <div className='flex items-center gap-2 text-red-700 dark:text-red-400'>
            <ShieldAlert className='size-5' />
            <h3 className='font-semibold'>
              {t('temporary_works.banner.breach_title')}
            </h3>
            <span
              data-testid='breach-count'
              className='ms-auto rounded bg-red-600 px-2 py-0.5 text-xs font-semibold text-white'
            >
              {t('temporary_works.banner.breach_count', {
                count: breaches.length,
              })}
            </span>
          </div>
          <ul className='mt-2 grid gap-1 text-sm'>
            {breaches.map((b, i) => (
              <li key={`${b.item_id}-${i}`} data-testid='breach-reason'>
                <span className='font-medium'>
                  {b.reference ?? ''}
                  {b.title ? ` · ${b.title}` : ''}
                </span>
                {': '}
                {b.reason}
              </li>
            ))}
          </ul>
        </section>
      ) : (
        <section
          role='status'
          data-testid='no-breach-banner'
          className='flex items-start gap-2 rounded-md border border-green-600/40 bg-green-600/10 p-4'
        >
          <ShieldCheck className='mt-0.5 size-5 text-green-700 dark:text-green-400' />
          <div>
            <h3 className='font-semibold text-green-700 dark:text-green-400'>
              {t('temporary_works.banner.none_title')}
            </h3>
            <p className='text-sm text-muted-foreground'>
              {t('temporary_works.banner.none_help')}
            </p>
          </div>
        </section>
      )}
      {overdueToLoad > 0 || overdueToStrike > 0 ? (
        <section
          data-testid='overdue-banner'
          className='flex flex-wrap gap-3 rounded-md border border-amber-500/40 bg-amber-500/10 px-4 py-2 text-sm'
        >
          {overdueToLoad > 0 ? (
            <span data-testid='overdue-load'>
              {t('temporary_works.banner.overdue_load', {
                count: overdueToLoad,
              })}
            </span>
          ) : null}
          {overdueToStrike > 0 ? (
            <span data-testid='overdue-strike'>
              {t('temporary_works.banner.overdue_strike', {
                count: overdueToStrike,
              })}
            </span>
          ) : null}
        </section>
      ) : null}
    </div>
  )
}
