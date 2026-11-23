import { useTranslation } from 'react-i18next'
import type { Finding } from './api'

/** The non-blocking warnings the server returned with a save. They never stop the save. */
export function WarningsList({ warnings }: { warnings: Finding[] }) {
  const { t } = useTranslation()
  if (warnings.length === 0) return null
  return (
    <div
      role='status'
      data-testid='warnings-list'
      className='rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-sm'
    >
      <p className='font-medium text-amber-700 dark:text-amber-400'>
        {t('temporary_works.warnings_saved')}
      </p>
      <ul className='mt-1 list-disc ps-5'>
        {warnings.map((w, i) => (
          <li key={`${w.rule}-${i}`} data-rule={w.rule}>
            {w.message}
          </li>
        ))}
      </ul>
    </div>
  )
}
