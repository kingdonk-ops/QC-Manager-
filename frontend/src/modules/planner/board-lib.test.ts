import { describe, expect, it } from 'vitest'
import {
  anchorsLabel,
  byCell,
  dayHeading,
  doubleBooked,
  parseMembers,
} from './board-lib'

const rows = [
  { id: 1, anchor_id: 10, work_date: '2026-11-24', crew_id: 1 },
  { id: 2, anchor_id: 10, work_date: '2026-11-24', crew_id: 2 },
  { id: 3, anchor_id: 11, work_date: '2026-11-24', crew_id: 1 },
  { id: 4, anchor_id: 11, work_date: '2026-11-25', crew_id: 2 },
]

describe('byCell', () => {
  it('groups assignments by work anchor and day', () => {
    const cells = byCell(rows)
    expect(cells.get('10|2026-11-24')?.map((r) => r.id)).toEqual([1, 2])
    expect(cells.get('11|2026-11-25')?.map((r) => r.id)).toEqual([4])
    expect(cells.get('10|2026-11-25')).toBeUndefined()
  })
})

describe('doubleBooked', () => {
  it('flags a crew on two work anchors the same day', () => {
    expect([...doubleBooked(rows)]).toEqual(['1|2026-11-24'])
  })
})

describe('dayHeading', () => {
  it('reads the ISO date as a local date', () => {
    expect(dayHeading('2026-11-29')).toMatchObject({ day: 29, weekend: true })
    expect(dayHeading('2026-11-24').weekend).toBe(false)
  })
})

describe('parseMembers', () => {
  it('takes one member per line as name, trade', () => {
    expect(parseMembers('J. Miller, Rigger\n\n K. Thorne \nA, B, C')).toEqual([
      { name: 'J. Miller', trade: 'Rigger' },
      { name: 'K. Thorne', trade: null },
      { name: 'A', trade: 'B, C' },
    ])
  })
})

describe('anchorsLabel', () => {
  it('lists the RSWs with the note the activity name gave', () => {
    expect(
      anchorsLabel({
        anchors: [
          { code: '728', qualifier: 'OHP' },
          { code: '729', qualifier: null },
        ],
      })
    ).toBe('728 (OHP), 729')
    expect(anchorsLabel({ anchors: [] })).toBe('')
  })
})
