/** Pure helpers for the look-ahead board. */

export type CellAssignment = {
  id: number
  anchor_id: number
  work_date: string
  crew_id: number
}

export const cellKey = (anchorId: number, day: string) => `${anchorId}|${day}`

/** Assignments grouped by board cell (work anchor × day). */
export function byCell<T extends CellAssignment>(rows: T[]): Map<string, T[]> {
  const out = new Map<string, T[]>()
  for (const r of rows) {
    const key = cellKey(r.anchor_id, r.work_date)
    const list = out.get(key)
    if (list) list.push(r)
    else out.set(key, [r])
  }
  return out
}

/** Days a crew is on more than one work anchor (shown as a warning on its chips). */
export function doubleBooked<T extends CellAssignment>(rows: T[]): Set<string> {
  const anchors = new Map<string, Set<number>>()
  for (const r of rows) {
    const key = `${r.crew_id}|${r.work_date}`
    const set = anchors.get(key) ?? new Set<number>()
    set.add(r.anchor_id)
    anchors.set(key, set)
  }
  return new Set(
    [...anchors.entries()].filter(([, s]) => s.size > 1).map(([k]) => k)
  )
}

export type Readiness = 'ready' | 'warning' | 'blocked' | string

export function readinessTone(state: Readiness) {
  if (state === 'blocked') return 'bg-red-500/15 text-red-700 dark:text-red-400'
  if (state === 'warning')
    return 'bg-amber-500/15 text-amber-700 dark:text-amber-400'
  return 'bg-green-500/15 text-green-700 dark:text-green-400'
}

/** `Mon 24` style column heading for an ISO date, without time-zone drift. */
export function dayHeading(iso: string) {
  const [y, m, d] = iso.split('-').map(Number)
  const date = new Date(y, m - 1, d)
  return {
    weekday: date.toLocaleDateString(undefined, { weekday: 'short' }),
    day: d,
    weekend: date.getDay() === 0 || date.getDay() === 6,
  }
}

/** Parse crew members typed one per line as `Name, Trade`. */
export function parseMembers(text: string) {
  return text
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const [name, ...rest] = line.split(',')
      const trade = rest.join(',').trim()
      return { name: name.trim(), trade: trade || null }
    })
}

/** The RSWs a programme activity is linked to, with the note its name gave (OHP, Access...). */
export function anchorsLabel(a: {
  anchors: { code: string; qualifier?: string | null }[]
}): string {
  return a.anchors
    .map((x) => (x.qualifier ? `${x.code} (${x.qualifier})` : x.code))
    .join(', ')
}
