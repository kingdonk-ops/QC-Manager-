/**
 * Counts and averages over the items already loaded on the page, for the insights panel. They are descriptive only:
 * no safety figure comes from here (breaches, gates, overdue and clearance are the server's).
 */
import { MAIN_FLOW, ON_HOLD } from './rules'

export type InsightItem = {
  family: string
  status: string
  design_check_category?: number | null
  created_at?: string | null
  updated_at?: string | null
}

export type Insights = {
  total: number
  byFamily: [string, number][]
  byStatus: [string, number][]
  byCategory: [string, number][]
  perMonth: { month: string; count: number }[]
  bearingLoad: number
  designCleared: number
  onHold: number
  /** Whole register average in days, one decimal; absent when no item has a created time. */
  averageDays: number | null
}

const DAY_MS = 86_400_000
const BEARING = new Set(['loaded', 'in_use'])
/** Design checked and every later main-flow status; on hold is not counted. */
const CLEARED = new Set<string>(
  MAIN_FLOW.slice(MAIN_FLOW.indexOf('design_checked'))
)
const ENDED = new Set(['struck', 'removed'])

function tally(values: string[]): [string, number][] {
  const counts = new Map<string, number>()
  for (const v of values) counts.set(v, (counts.get(v) ?? 0) + 1)
  return [...counts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
}

/**
 * Average days an item has been on the register: to now for a live item, to its last update for a struck or removed
 * one, never negative.
 */
export function averageDaysOnRegister(
  items: InsightItem[],
  nowMs: number
): number | null {
  const spans: number[] = []
  for (const i of items) {
    const start = i.created_at ? Date.parse(i.created_at) : NaN
    if (Number.isNaN(start)) continue
    const stop =
      ENDED.has(i.status) && i.updated_at ? Date.parse(i.updated_at) : nowMs
    spans.push(Math.max(0, ((Number.isNaN(stop) ? nowMs : stop) - start) / DAY_MS))
  }
  if (spans.length === 0) return null
  return Math.round((spans.reduce((a, b) => a + b, 0) / spans.length) * 10) / 10
}

export function buildInsights(items: InsightItem[], nowMs: number): Insights {
  const months = items
    .map((i) => (i.created_at ? i.created_at.slice(0, 7) : ''))
    .filter(Boolean)
  return {
    total: items.length,
    byFamily: tally(items.map((i) => i.family)),
    byStatus: tally(items.map((i) => i.status)),
    byCategory: tally(
      items.map((i) =>
        i.design_check_category === null || i.design_check_category === undefined
          ? 'unassigned'
          : String(i.design_check_category)
      )
    ),
    perMonth: tally(months)
      .map(([month, count]) => ({ month, count }))
      .sort((a, b) => a.month.localeCompare(b.month)),
    bearingLoad: items.filter((i) => BEARING.has(i.status)).length,
    designCleared: items.filter((i) => CLEARED.has(i.status)).length,
    onHold: items.filter((i) => i.status === ON_HOLD).length,
    averageDays: averageDaysOnRegister(items, nowMs),
  }
}
