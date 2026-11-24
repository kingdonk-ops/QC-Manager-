import { describe, expect, it } from 'vitest'
import { render } from 'vitest-browser-react'
import { Insights } from './insights'
import {
  averageDaysOnRegister,
  buildInsights,
  type InsightItem,
} from './insights-data'

const NOW = Date.parse('2026-03-31T00:00:00Z')

const items: InsightItem[] = [
  {
    family: 'propping',
    status: 'loaded',
    design_check_category: 1,
    created_at: '2026-01-10T00:00:00Z',
    updated_at: '2026-01-10T00:00:00Z',
  },
  {
    family: 'propping',
    status: 'in_use',
    design_check_category: 3,
    created_at: '2026-01-20T00:00:00Z',
    updated_at: '2026-02-01T00:00:00Z',
  },
  {
    family: 'scaffold',
    status: 'on_hold',
    design_check_category: null,
    created_at: '2026-02-05T00:00:00Z',
    updated_at: '2026-02-05T00:00:00Z',
  },
  {
    family: 'scaffold',
    status: 'struck',
    design_check_category: 1,
    created_at: '2026-02-10T00:00:00Z',
    updated_at: '2026-02-20T00:00:00Z',
  },
]

describe('buildInsights', () => {
  it('counts by family, status and category, with unassigned', () => {
    const r = buildInsights(items, NOW)
    expect(r.total).toBe(4)
    expect(r.byFamily).toEqual([
      ['propping', 2],
      ['scaffold', 2],
    ])
    expect(r.byCategory).toContainEqual(['unassigned', 1])
    expect(r.byCategory).toContainEqual(['1', 2])
    expect(r.byStatus.reduce((n, [, c]) => n + c, 0)).toBe(4)
  })

  it('counts items bearing load as loaded plus in use, design cleared and on hold', () => {
    const r = buildInsights(items, NOW)
    expect(r.bearingLoad).toBe(2)
    expect(r.designCleared).toBe(3)
    expect(r.onHold).toBe(1)
  })

  it('counts items added per month in month order', () => {
    expect(buildInsights(items, NOW).perMonth).toEqual([
      { month: '2026-01', count: 2 },
      { month: '2026-02', count: 2 },
    ])
  })
})

describe('averageDaysOnRegister', () => {
  it('measures a live item to now and a struck item to its last update', () => {
    const live: InsightItem = {
      family: 'other',
      status: 'loaded',
      created_at: '2026-03-21T00:00:00Z',
    }
    const struck: InsightItem = {
      family: 'other',
      status: 'struck',
      created_at: '2026-03-01T00:00:00Z',
      updated_at: '2026-03-05T00:00:00Z',
    }
    // 10 days live and 4 days to the last update.
    expect(averageDaysOnRegister([live, struck], NOW)).toBe(7)
  })

  it('is never negative when the clock is behind the created time', () => {
    const future: InsightItem = {
      family: 'other',
      status: 'loaded',
      created_at: '2026-06-01T00:00:00Z',
    }
    expect(averageDaysOnRegister([future], NOW)).toBe(0)
  })

  it('is absent when no item has a created time', () => {
    expect(averageDaysOnRegister([{ family: 'other', status: 'loaded' }], NOW)).toBeNull()
  })
})

describe('Insights panel', () => {
  it('shows the counts, the overdue figure the server gave and the average', async () => {
    const screen = await render(
      <Insights items={items} overdueToLoad={2} nowMs={NOW} />
    )
    await expect
      .element(screen.getByTestId('insight-bearing-load'))
      .toHaveTextContent('2')
    await expect
      .element(screen.getByTestId('insight-on-hold'))
      .toHaveTextContent('1')
    await expect
      .element(screen.getByTestId('insight-overdue-load'))
      .toHaveTextContent('2')
    await expect
      .element(screen.getByTestId('insight-families'))
      .toHaveTextContent('temporary_works.family.propping')
    expect(screen.getByTestId('insights-truncated').elements()).toHaveLength(0)
  })

  it('says when it covers only part of the register', async () => {
    const screen = await render(
      <Insights
        items={items}
        overdueToLoad={0}
        nowMs={NOW}
        truncated={{ shown: 4, total: 250 }}
      />
    )
    await expect
      .element(screen.getByTestId('insights-truncated'))
      .toBeInTheDocument()
  })

  it('shows a dash for the average of an empty register', async () => {
    const screen = await render(
      <Insights items={[]} overdueToLoad={0} nowMs={NOW} />
    )
    await expect
      .element(screen.getByTestId('insight-average-days'))
      .toHaveTextContent('—')
  })
})
