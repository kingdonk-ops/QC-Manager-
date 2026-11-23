import { useMemo, useState } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { useTranslation } from 'react-i18next'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { buildInsights, type InsightItem } from './insights-data'
import { categoryKey, familyKey, statusKey } from './rules'

function Counts({
  title,
  rows,
  label,
  testId,
}: {
  title: string
  rows: [string, number][]
  label: (key: string) => string
  testId: string
}) {
  const { t } = useTranslation()
  return (
    <Card className='gap-2 py-3' data-testid={testId}>
      <CardHeader className='px-4'>
        <CardTitle className='text-sm'>{title}</CardTitle>
      </CardHeader>
      <CardContent className='px-4'>
        {rows.length === 0 ? (
          <p className='text-xs text-muted-foreground'>
            {t('temporary_works.insights.none')}
          </p>
        ) : (
          <ul className='grid gap-0.5 text-sm'>
            {rows.map(([key, count]) => (
              <li key={key} className='flex justify-between' data-key={key}>
                <span>{label(key)}</span>
                <span className='tabular-nums'>{count}</span>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  )
}

function Figure({
  label,
  value,
  testId,
}: {
  label: string
  value: string | number
  testId: string
}) {
  return (
    <div className='rounded-md border p-3' data-testid={testId}>
      <p className='text-xs text-muted-foreground'>{label}</p>
      <p className='text-lg font-semibold tabular-nums'>{value}</p>
    </div>
  )
}

/**
 * Descriptive insights over the loaded items. `overdueToLoad` is the server's own count, shown as the register has it.
 * `truncated` says the register holds more items than were loaded, so the panel covers part of it.
 */
export function Insights({
  items,
  overdueToLoad,
  truncated,
  nowMs,
}: {
  items: InsightItem[]
  overdueToLoad: number
  truncated?: { shown: number; total: number } | null
  /** The clock, for tests; the page passes nothing. */
  nowMs?: number
}) {
  const { t } = useTranslation()
  // The clock is read once when the panel first renders, not on every render.
  const [mountedAt] = useState(() => Date.now())
  const data = useMemo(
    () => buildInsights(items, nowMs ?? mountedAt),
    [items, nowMs, mountedAt]
  )
  return (
    <section className='grid gap-3' data-testid='insights'>
      <h3 className='text-sm font-semibold'>
        {t('temporary_works.insights.title')}
      </h3>
      {truncated ? (
        <p className='text-xs text-muted-foreground' data-testid='insights-truncated'>
          {t('temporary_works.insights.truncated', { shown: truncated.shown })}
        </p>
      ) : null}
      <div className='grid grid-cols-2 gap-3 md:grid-cols-5'>
        <Figure
          testId='insight-bearing-load'
          label={t('temporary_works.insights.bearing_load')}
          value={data.bearingLoad}
        />
        <Figure
          testId='insight-design-cleared'
          label={t('temporary_works.insights.design_cleared')}
          value={data.designCleared}
        />
        <Figure
          testId='insight-on-hold'
          label={t('temporary_works.insights.on_hold')}
          value={data.onHold}
        />
        <Figure
          testId='insight-overdue-load'
          label={t('temporary_works.insights.overdue_to_load')}
          value={overdueToLoad}
        />
        <Figure
          testId='insight-average-days'
          label={t('temporary_works.insights.average_days')}
          value={data.averageDays === null ? '—' : data.averageDays}
        />
      </div>
      <div className='grid gap-3 md:grid-cols-3'>
        <Counts
          testId='insight-families'
          title={t('temporary_works.insights.by_family')}
          rows={data.byFamily}
          label={(k) => t(familyKey(k))}
        />
        <Counts
          testId='insight-statuses'
          title={t('temporary_works.insights.by_status')}
          rows={data.byStatus}
          label={(k) => t(statusKey(k))}
        />
        <Counts
          testId='insight-categories'
          title={t('temporary_works.insights.by_category')}
          rows={data.byCategory}
          label={(k) =>
            t(categoryKey(k === 'unassigned' ? null : Number(k)))
          }
        />
      </div>
      <Card className='gap-2 py-3' data-testid='insight-months'>
        <CardHeader className='px-4'>
          <CardTitle className='text-sm'>
            {t('temporary_works.insights.per_month')}
          </CardTitle>
        </CardHeader>
        <CardContent className='px-4'>
          {data.perMonth.length === 0 ? (
            <p className='text-xs text-muted-foreground'>
              {t('temporary_works.insights.none')}
            </p>
          ) : (
            <ResponsiveContainer width='100%' height={180}>
              <BarChart
                data={data.perMonth}
                margin={{ top: 8, right: 8, bottom: 0, left: 0 }}
              >
                <CartesianGrid strokeDasharray='3 3' className='stroke-border' />
                <XAxis dataKey='month' fontSize={12} />
                <YAxis allowDecimals={false} fontSize={12} width={32} />
                <Tooltip />
                <Bar dataKey='count' fill='#2563eb' />
              </BarChart>
            </ResponsiveContainer>
          )}
        </CardContent>
      </Card>
    </section>
  )
}
