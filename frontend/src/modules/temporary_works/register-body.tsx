import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { Item, Permit, Rollup } from './api'
import { applyFilters, NO_FILTERS, type Filters } from './filter-rules'
import { HeadlineFigures } from './headline-figures'
import { Insights } from './insights'
import { ItemRows, type RowActions } from './item-rows'
import { RegisterFilters } from './register-filters'
import { SafetyBanners } from './safety-banners'

/**
 * The register as the server reported it: banners and figures from the rollup, the items as expandable rows, and
 * insights over the loaded items. It holds no rule logic; every safety figure arrives ready-made.
 */
export function RegisterBody({
  rollup,
  items,
  total,
  permits,
  loading,
  has,
  actions,
  nowMs,
}: {
  rollup?: Rollup
  items: Item[]
  /** The number of items the server counted, which can exceed the items loaded. */
  total: number
  permits: Permit[]
  loading?: boolean
  has: (permission: string) => boolean
  actions: RowActions
  nowMs?: number
}) {
  const { t } = useTranslation()
  const [filters, setFilters] = useState<Filters>(NO_FILTERS)
  const shown = useMemo(() => applyFilters(items, filters), [items, filters])
  const breachIds = useMemo(
    () =>
      new Set(
        (rollup?.breaches ?? [])
          .map((b) => b.item_id)
          .filter((id): id is number => typeof id === 'number')
      ),
    [rollup]
  )
  const filtered = Object.values(filters).some(Boolean)
  const truncated = total > items.length
  const counts = rollup?.status_counts ?? {}
  return (
    <div className='grid gap-4'>
      {rollup ? (
        <>
          <SafetyBanners
            breaches={rollup.breaches}
            overdueToLoad={rollup.overdue_to_load.length}
            overdueToStrike={rollup.overdue_to_strike.length}
          />
          <HeadlineFigures
            total={rollup.total}
            clearance={rollup.design_clearance}
            bearingLoad={(counts.loaded ?? 0) + (counts.in_use ?? 0)}
            breaches={rollup.breaches.length}
          />
        </>
      ) : null}
      <RegisterFilters
        filters={filters}
        onChange={setFilters}
        shown={shown.length}
        total={items.length}
      />
      {truncated ? (
        <p
          className='text-xs text-muted-foreground'
          data-testid='rows-truncated'
        >
          {t('temporary_works.truncated', { shown: items.length, total })}
        </p>
      ) : null}
      <ItemRows
        items={shown}
        permits={permits}
        gates={rollup?.gates ?? []}
        breachIds={breachIds}
        warnings={rollup?.warnings ?? []}
        has={has}
        loading={loading}
        filtered={filtered}
        actions={actions}
      />
      {!loading ? (
        <Insights
          items={items}
          overdueToLoad={rollup?.overdue_to_load.length ?? 0}
          truncated={truncated ? { shown: items.length, total } : null}
          nowMs={nowMs}
        />
      ) : null}
    </div>
  )
}
