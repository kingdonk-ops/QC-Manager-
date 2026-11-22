/** Colours of the Gantt, written into the SVG as attributes so exports look the same. */
import type { Activity } from './api'

export const COLORS = {
  pending: '#64748b',
  in_progress: '#2563eb',
  completed: '#16a34a',
  critical: '#dc2626',
  summary: '#334155',
  baseline: '#9ca3af',
  today: '#f97316',
  dataDate: '#7c3aed',
  link: '#64748b',
  nonWorking: '#94a3b8',
}

export function barColor(a: Activity): string {
  if (a.type === 'summary') return COLORS.summary
  if (a.is_critical && a.status !== 'completed') return COLORS.critical
  return (
    COLORS[a.status as 'pending' | 'in_progress' | 'completed'] ??
    COLORS.pending
  )
}
