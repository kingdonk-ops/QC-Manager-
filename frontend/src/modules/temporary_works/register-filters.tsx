import { useTranslation } from 'react-i18next'
import { Input } from '@/components/ui/input'
import { NativeSelect } from '@/components/native-select'
import type { Filters } from './filter-rules'
import {
  CATEGORIES,
  FAMILIES,
  ITEM_STATUSES,
  categoryKey,
  familyKey,
  statusKey,
} from './rules'

/** Narrows the loaded items by search text, status, family and category, and says how many are showing. */
export function RegisterFilters({
  filters,
  onChange,
  shown,
  total,
}: {
  filters: Filters
  onChange: (next: Filters) => void
  shown: number
  total: number
}) {
  const { t } = useTranslation()
  const set = (patch: Partial<Filters>) => onChange({ ...filters, ...patch })
  return (
    <div className='flex flex-wrap items-center gap-2'>
      <Input
        className='h-8 w-60'
        aria-label={t('temporary_works.search')}
        placeholder={t('temporary_works.search')}
        value={filters.search}
        onChange={(e) => set({ search: e.target.value })}
      />
      <NativeSelect
        className='h-8 w-48'
        aria-label={t('temporary_works.item_status')}
        placeholder={t('temporary_works.all_statuses')}
        options={ITEM_STATUSES.map((s) => ({
          value: s,
          label: t(statusKey(s)),
        }))}
        value={filters.status}
        onChange={(e) => set({ status: e.target.value })}
      />
      <NativeSelect
        className='h-8 w-48'
        aria-label={t('temporary_works.item.family')}
        placeholder={t('temporary_works.all_families')}
        options={FAMILIES.map((f) => ({ value: f, label: t(familyKey(f)) }))}
        value={filters.family}
        onChange={(e) => set({ family: e.target.value })}
      />
      <NativeSelect
        className='h-8 w-44'
        aria-label={t('temporary_works.item.category')}
        placeholder={t('temporary_works.all_categories')}
        options={[
          ...CATEGORIES.map((c) => ({
            value: String(c),
            label: t(categoryKey(c)),
          })),
          { value: 'unassigned', label: t(categoryKey(null)) },
        ]}
        value={filters.category}
        onChange={(e) => set({ category: e.target.value })}
      />
      <span
        className='ms-auto text-sm text-muted-foreground'
        data-testid='showing-count'
        data-shown={shown}
        data-total={total}
      >
        {t('temporary_works.showing', { shown, total })}
      </span>
    </div>
  )
}
