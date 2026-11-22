/** Pure helpers for the P6 screens. */

export type Sample = { name: string; code?: string | null }

/**
 * One sample per line. `A1000 | 101 / B / 305` gives an Activity ID and a name; a line without `|` is a name.
 */
export function parseSamples(text: string): Sample[] {
  return text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .slice(0, 200)
    .map((line) => {
      const bar = line.indexOf('|')
      if (bar < 0) return { name: line }
      return {
        code: line.slice(0, bar).trim() || null,
        name: line.slice(bar + 1).trim(),
      }
    })
}

const LABELS: Record<string, string> = {
  planned_start: 'start',
  planned_finish: 'finish',
  duration: 'duration',
  late_finish: 'late finish',
  status_code: 'status',
  actual_start: 'actual start',
  actual_finish: 'actual finish',
  percent_complete: '%',
  total_float_hours: 'float (h)',
  longest_path: 'longest path',
  wbs: 'WBS',
  name: 'name',
  schedule_state: 'state',
  p6_activity_id: 'Activity ID',
}

function show(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value).replace(/^WBS:/, '')
}

/** "start 2026-03-02 → 2026-03-05; finish …" for the fields that differ. New activities show nothing. */
export function describeChange(change: {
  change_type: string
  old: Record<string, unknown>
  new: Record<string, unknown>
}): string {
  if (change.change_type === 'new' || change.change_type === 'adopted')
    return ''
  return Object.keys(change.new)
    .filter((k) => show(change.old[k]) !== show(change.new[k]))
    .map(
      (k) =>
        `${LABELS[k] ?? k.replace(/_/g, ' ')} ${show(change.old[k])} → ${show(change.new[k])}`
    )
    .join('; ')
}

/** Positive days slip later, negative pull earlier. */
export function shiftLabel(days: unknown): string {
  const n = Number(days)
  if (!Number.isFinite(n) || n === 0) return ''
  return n > 0 ? `+${n} d` : `${n} d`
}

export const CHANGE_TYPES = [
  'new',
  'adopted',
  'name_changed',
  'dates_changed',
  'wbs_moved',
  'status_changed',
  'codes_or_udfs_changed',
  'facts_changed',
  'renumbered',
  'removed',
  'restored',
] as const
