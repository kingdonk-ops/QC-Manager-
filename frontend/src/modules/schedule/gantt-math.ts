/**
 * Pure helpers for the SVG Gantt: dates as whole UTC day numbers, the zoom levels and their
 * timescale, the WBS tree flattened for display, and the routing of dependency arrows.
 */

export type Zoom = 'day' | 'week' | 'month' | 'quarter' | 'year'

export const ZOOMS: Zoom[] = ['day', 'week', 'month', 'quarter', 'year']

/** Pixels per calendar day at each zoom. */
export const PX_PER_DAY: Record<Zoom, number> = {
  day: 28,
  week: 8,
  month: 3,
  quarter: 1.2,
  year: 0.4,
}

export const ROW_HEIGHT = 28
export const HEADER_HEIGHT = 44
const DAY_MS = 86_400_000

/** `2026-01-05` → days since 1970-01-01 (UTC), so arithmetic never meets a DST change. */
export function dayNumber(iso: string): number {
  const [y, m, d] = iso.slice(0, 10).split('-').map(Number)
  return Math.round(Date.UTC(y, m - 1, d) / DAY_MS)
}

export function isoOf(day: number): string {
  return new Date(day * DAY_MS).toISOString().slice(0, 10)
}

/** Monday 0 .. Sunday 6, matching the backend's working-day numbers. */
export function weekday(day: number): number {
  return (new Date(day * DAY_MS).getUTCDay() + 6) % 7
}

function parts(day: number) {
  const d = new Date(day * DAY_MS)
  return { y: d.getUTCFullYear(), m: d.getUTCMonth(), d: d.getUTCDate() }
}

function monthStart(y: number, m: number): number {
  return Math.round(Date.UTC(y, m, 1) / DAY_MS)
}

export type Tick = { start: number; end: number; label: string }

const MONTHS = [
  'Jan',
  'Feb',
  'Mar',
  'Apr',
  'May',
  'Jun',
  'Jul',
  'Aug',
  'Sep',
  'Oct',
  'Nov',
  'Dec',
]

function months(from: number, to: number, withYear: boolean): Tick[] {
  const out: Tick[] = []
  let { y, m } = parts(from)
  let start = monthStart(y, m)
  while (start < to) {
    const next = m === 11 ? monthStart(y + 1, 0) : monthStart(y, m + 1)
    out.push({
      start,
      end: next,
      label: withYear ? `${MONTHS[m]} ${y}` : MONTHS[m],
    })
    m = (m + 1) % 12
    if (m === 0) y += 1
    start = next
  }
  return out
}

function quarters(from: number, to: number): Tick[] {
  const out: Tick[] = []
  let { y, m } = parts(from)
  m = m - (m % 3)
  let start = monthStart(y, m)
  while (start < to) {
    const nm = m + 3
    const next = nm >= 12 ? monthStart(y + 1, nm - 12) : monthStart(y, nm)
    out.push({ start, end: next, label: `Q${m / 3 + 1}` })
    if (nm >= 12) {
      y += 1
      m = nm - 12
    } else m = nm
    start = next
  }
  return out
}

function years(from: number, to: number): Tick[] {
  const out: Tick[] = []
  let { y } = parts(from)
  let start = monthStart(y, 0)
  while (start < to) {
    const next = monthStart(y + 1, 0)
    out.push({ start, end: next, label: String(y) })
    y += 1
    start = next
  }
  return out
}

function days(from: number, to: number): Tick[] {
  const out: Tick[] = []
  for (let day = from; day < to; day++)
    out.push({ start: day, end: day + 1, label: String(parts(day).d) })
  return out
}

function weeks(from: number, to: number): Tick[] {
  const out: Tick[] = []
  let start = from - weekday(from)
  while (start < to) {
    const { d, m } = parts(start)
    out.push({ start, end: start + 7, label: `${d} ${MONTHS[m]}` })
    start += 7
  }
  return out
}

/** The two rows of the timescale header for a zoom level. */
export function timescale(
  zoom: Zoom,
  from: number,
  to: number
): { top: Tick[]; bottom: Tick[] } {
  switch (zoom) {
    case 'day':
      return { top: months(from, to, true), bottom: days(from, to) }
    case 'week':
      return { top: months(from, to, true), bottom: weeks(from, to) }
    case 'month':
      return { top: years(from, to), bottom: months(from, to, false) }
    case 'quarter':
      return { top: years(from, to), bottom: quarters(from, to) }
    default:
      return { top: years(from, to), bottom: quarters(from, to) }
  }
}

/** The span to draw: every date in the schedule, padded so bars never touch the edge. */
export function chartRange(
  dates: (string | null | undefined)[],
  zoom: Zoom
): { from: number; to: number } {
  const known = dates.filter((d): d is string => !!d).map(dayNumber)
  const today = Math.floor(Date.now() / DAY_MS)
  const min = known.length ? Math.min(...known) : today
  const max = known.length ? Math.max(...known) : today + 30
  const pad = { day: 7, week: 14, month: 45, quarter: 90, year: 180 }[zoom]
  return { from: min - pad, to: max + pad + 1 }
}

export type TreeRow<T> = {
  item: T
  depth: number
  hasChildren: boolean
}

/** Activities in WBS order with their depth, leaving out the children of collapsed rows. */
export function flattenTree<
  T extends { id: number; parent_id?: number | null },
>(items: T[], collapsed: ReadonlySet<number>): TreeRow<T>[] {
  const ids = new Set(items.map((i) => i.id))
  const children = new Map<number | null, T[]>()
  for (const item of items) {
    const parent =
      item.parent_id != null && ids.has(item.parent_id) ? item.parent_id : null
    const list = children.get(parent) ?? []
    list.push(item)
    children.set(parent, list)
  }
  const out: TreeRow<T>[] = []
  const seen = new Set<number>()
  const walk = (parent: number | null, depth: number) => {
    for (const item of children.get(parent) ?? []) {
      if (seen.has(item.id)) continue
      seen.add(item.id)
      const kids = children.get(item.id) ?? []
      out.push({ item, depth, hasChildren: kids.length > 0 })
      if (!collapsed.has(item.id)) walk(item.id, depth + 1)
    }
  }
  walk(null, 0)
  return out
}

export type Point = { x: number; y: number }

/**
 * An orthogonal path for a link. `from` leaves the predecessor's start (SS, SF) or finish (FS, FF);
 * `to` enters the successor's start (FS, SS) from the left or its finish (FF, SF) from the right.
 */
export function linkPath(type: string, from: Point, to: Point): string {
  const gap = 8
  const outDir = type === 'FS' || type === 'FF' ? 1 : -1
  const inDir = type === 'FS' || type === 'SS' ? 1 : -1
  const x1 = from.x + outDir * gap
  const x2 = to.x - inDir * gap
  if (outDir !== inDir) {
    // SS and FF: one turn beyond whichever end sticks out further.
    const turn = outDir === 1 ? Math.max(x1, x2) : Math.min(x1, x2)
    return `M${from.x},${from.y} H${turn} V${to.y} H${to.x}`
  }
  // FS and SF: straight down when there's room, otherwise around between the rows.
  if ((outDir === 1 && x1 <= x2) || (outDir === -1 && x1 >= x2)) {
    return `M${from.x},${from.y} H${x1} V${to.y} H${to.x}`
  }
  const mid = to.y > from.y ? to.y - ROW_HEIGHT / 2 : to.y + ROW_HEIGHT / 2
  return `M${from.x},${from.y} H${x1} V${mid} H${x2} V${to.y} H${to.x}`
}

/** Whole days moved by a drag of `dx` pixels at this zoom. */
export function snapDays(dx: number, zoom: Zoom): number {
  return Math.round(dx / PX_PER_DAY[zoom])
}
