import { describe, expect, it } from 'vitest'
import {
  chartRange,
  dayNumber,
  flattenTree,
  isoOf,
  linkPath,
  snapDays,
  timescale,
  weekday,
} from './gantt-math'
import { parseSections } from './sections'

describe('gantt dates', () => {
  it('round-trips ISO dates through day numbers', () => {
    const day = dayNumber('2026-01-05')
    expect(isoOf(day)).toBe('2026-01-05')
    expect(isoOf(day + 7)).toBe('2026-01-12')
    expect(weekday(day)).toBe(0) // Monday
    expect(weekday(day + 6)).toBe(6) // Sunday
  })

  it('pads the range to the zoom', () => {
    const r = chartRange(['2026-01-05', null, '2026-01-30'], 'day')
    expect(isoOf(r.from)).toBe('2025-12-29')
    expect(isoOf(r.to - 1)).toBe('2026-02-06')
  })

  it('snaps a drag to whole days', () => {
    expect(snapDays(30, 'day')).toBe(1)
    expect(snapDays(-23, 'week')).toBe(-3)
  })
})

describe('timescale', () => {
  const from = dayNumber('2026-01-01')
  const to = dayNumber('2026-04-01')

  it('labels months over days', () => {
    const { top, bottom } = timescale('day', from, from + 3)
    expect(top[0].label).toBe('Jan 2026')
    expect(bottom.map((t) => t.label)).toEqual(['1', '2', '3'])
  })

  it('starts weeks on Monday', () => {
    const { bottom } = timescale('week', from, from + 10)
    expect(isoOf(bottom[0].start)).toBe('2025-12-29')
    expect(bottom[1].label).toBe('5 Jan')
  })

  it('groups months into years and quarters', () => {
    expect(timescale('month', from, to).bottom.map((t) => t.label)).toEqual([
      'Jan',
      'Feb',
      'Mar',
    ])
    const q = timescale('quarter', from, dayNumber('2026-12-31'))
    expect(q.bottom.map((t) => t.label)).toEqual(['Q1', 'Q2', 'Q3', 'Q4'])
    expect(q.top.map((t) => t.label)).toEqual(['2026'])
    expect(timescale('year', from, dayNumber('2027-06-01')).top).toHaveLength(2)
  })
})

describe('flattenTree', () => {
  const items = [
    { id: 1, parent_id: null },
    { id: 2, parent_id: 1 },
    { id: 3, parent_id: 2 },
    { id: 4, parent_id: null },
    { id: 5, parent_id: 99 }, // parent not loaded: shown at the top
  ]

  it('orders children under parents with their depth', () => {
    const rows = flattenTree(items, new Set())
    expect(rows.map((r) => [r.item.id, r.depth, r.hasChildren])).toEqual([
      [1, 0, true],
      [2, 1, true],
      [3, 2, false],
      [4, 0, false],
      [5, 0, false],
    ])
  })

  it('hides the children of collapsed rows', () => {
    expect(flattenTree(items, new Set([1])).map((r) => r.item.id)).toEqual([
      1, 4, 5,
    ])
  })
})

describe('linkPath', () => {
  const a = { x: 100, y: 14 }

  it('routes finish-to-start straight down when there is room', () => {
    expect(linkPath('FS', a, { x: 200, y: 42 })).toBe('M100,14 H108 V42 H200')
  })

  it('routes finish-to-start around when the successor starts earlier', () => {
    expect(linkPath('FS', a, { x: 50, y: 70 })).toBe(
      'M100,14 H108 V56 H42 V70 H50'
    )
  })

  it('routes start-to-start and finish-to-finish with one turn', () => {
    expect(linkPath('SS', a, { x: 150, y: 42 })).toBe('M100,14 H92 V42 H150')
    expect(linkPath('FF', a, { x: 150, y: 42 })).toBe('M100,14 H158 V42 H150')
  })

  it('routes start-to-finish back to the left', () => {
    expect(linkPath('SF', a, { x: 40, y: 42 })).toBe('M100,14 H92 V42 H40')
  })
})

describe('parseSections', () => {
  it('reads JSON', () => {
    expect(
      parseSections('[{"code":"01","name":"Prelims","value":1000}]')
    ).toEqual([{ code: '01', name: 'Prelims', value: '1000' }])
  })

  it('reads one section per line', () => {
    expect(parseSections('01, Prelims, $1,000\n02;Cladding;500\n\n')).toEqual([
      { code: '01', name: 'Prelims', value: '1000' },
      { code: '02', name: 'Cladding', value: '500' },
    ])
  })
})
