import { describe, expect, it, vi } from 'vitest'
import { render } from 'vitest-browser-react'
import type { Activity, Dependency } from './api'
import { composeSvg } from './export-image'
import { GanttChart, TimescaleHeader } from './gantt-chart'
import { COLORS } from './gantt-colors'
import { dayNumber, flattenTree } from './gantt-math'

function activity(over: Partial<Activity>): Activity {
  return {
    id: 1,
    project_id: 1,
    code: 'A1',
    wbs_code: '1',
    name: 'Activity',
    parent_id: null,
    type: 'task',
    duration: 3,
    planned_start: '2026-01-05',
    planned_finish: '2026-01-07',
    actual_start: null,
    actual_finish: null,
    percent_complete: 0,
    status: 'pending',
    constraint_type: 'asap',
    constraint_date: null,
    resource: null,
    responsible_id: null,
    budget_hours: '0',
    budget_cost: '0',
    optimistic_duration: null,
    most_likely_duration: null,
    pessimistic_duration: null,
    notes: null,
    sort_order: 0,
    early_start: '2026-01-05',
    early_finish: '2026-01-07',
    late_start: '2026-01-05',
    late_finish: '2026-01-07',
    total_float: 0,
    free_float: 0,
    is_critical: false,
    driving_predecessor_ids: [],
    baseline_start: null,
    baseline_finish: null,
    start_variance: null,
    finish_variance: null,
    baseline_variance: null,
    ...over,
  } as Activity
}

const acts = [
  activity({ id: 1, code: 'S', wbs_code: '1', type: 'summary', duration: 5 }),
  activity({
    id: 2,
    code: 'A',
    wbs_code: '1.1',
    parent_id: 1,
    is_critical: true,
    percent_complete: 50,
    status: 'in_progress',
    baseline_start: '2026-01-05',
    baseline_finish: '2026-01-06',
  }),
  activity({
    id: 3,
    code: 'M',
    wbs_code: '2',
    type: 'milestone',
    duration: 0,
    early_start: '2026-01-08',
    early_finish: '2026-01-08',
    is_critical: true,
    driving_predecessor_ids: [2],
  }),
]
const deps: Dependency[] = [
  {
    id: 1,
    project_id: 1,
    predecessor_id: 2,
    successor_id: 3,
    type: 'FS',
    lag: 0,
  },
]
const from = dayNumber('2026-01-01')
const to = dayNumber('2026-01-20')

describe('GanttChart', () => {
  it('draws bars, a milestone, the critical path, baseline and links', async () => {
    const onSelect = vi.fn()
    const screen = await render(
      <GanttChart
        rows={flattenTree(acts, new Set())}
        dependencies={deps}
        zoom='day'
        from={from}
        to={to}
        workingDays={[0, 1, 2, 3, 4]}
        holidays={[]}
        dataDate='2026-01-06'
        showBaseline
        editable
        onSelect={onSelect}
      />
    )
    const svg = screen.container.querySelector('svg')!
    expect(svg.getAttribute('height')).toBe('84')
    expect(svg.querySelectorAll('[data-activity]')).toHaveLength(3)
    const critical = svg.querySelector(
      `[data-activity="2"] rect[fill="${COLORS.critical}"]`
    )
    expect(critical).not.toBeNull()
    expect(svg.textContent).toContain('CP')
    expect(svg.querySelector(`rect[fill="${COLORS.baseline}"]`)).not.toBeNull()
    expect(svg.querySelectorAll('path[marker-end]')).toHaveLength(1)
    expect(svg.textContent).toContain('Data date')
    // Weekends shaded in day view: 3, 4, 10, 11, 17, 18 January.
    expect(
      svg.querySelectorAll(`rect[fill="${COLORS.nonWorking}"]`)
    ).toHaveLength(6)
    critical!.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    expect(onSelect).toHaveBeenCalledWith(2)
  })

  it('composes one exportable SVG with labels and timescale', async () => {
    const screen = await render(
      <div>
        <TimescaleHeader zoom='week' from={from} to={to} />
        <GanttChart
          rows={flattenTree(acts, new Set())}
          dependencies={deps}
          zoom='week'
          from={from}
          to={to}
          workingDays={[0, 1, 2, 3, 4]}
          holidays={[]}
          showBaseline={false}
          editable={false}
        />
      </div>
    )
    const [header, body] = Array.from(screen.container.querySelectorAll('svg'))
    const out = composeSvg(
      header,
      body,
      acts.map((a) => ({ wbs: a.wbs_code, name: a.name, depth: 0 })),
      'Tower & Co'
    )
    expect(out.svg.startsWith('<svg xmlns="http://www.w3.org/2000/svg"')).toBe(
      true
    )
    expect(out.svg).toContain('Tower &amp; Co')
    expect(out.svg).toContain('5 Jan')
    expect(out.width).toBe(300 + (to - from) * 8)
    const parsed = new DOMParser().parseFromString(out.svg, 'image/svg+xml')
    expect(parsed.querySelector('parsererror')).toBeNull()
  })
})
