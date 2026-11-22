import { describe, expect, it } from 'vitest'
import { describeChange, parseSamples, shiftLabel } from './helpers'

describe('parseSamples', () => {
  it('reads one name per line, with an optional Activity ID before a bar', () => {
    expect(
      parseSamples('101 / B / 305\n\n  A1000 | 101 / P / 410.2  \n| x')
    ).toEqual([
      { name: '101 / B / 305' },
      { code: 'A1000', name: '101 / P / 410.2' },
      { code: null, name: 'x' },
    ])
  })
})

describe('describeChange', () => {
  it('lists only the fields that differ', () => {
    expect(
      describeChange({
        change_type: 'dates_changed',
        old: {
          planned_start: '2026-03-02',
          planned_finish: '2026-03-06',
          duration: 4,
        },
        new: {
          planned_start: '2026-03-05',
          planned_finish: '2026-03-09',
          duration: 4,
        },
      })
    ).toBe('start 2026-03-02 → 2026-03-05; finish 2026-03-06 → 2026-03-09')
  })

  it('shows WBS paths without their prefix and says nothing for new rows', () => {
    expect(
      describeChange({
        change_type: 'wbs_moved',
        old: { wbs: 'WBS:SITE.SHUT' },
        new: { wbs: null },
      })
    ).toBe('WBS SITE.SHUT → —')
    expect(
      describeChange({ change_type: 'new', old: {}, new: { name: 'x' } })
    ).toBe('')
  })
})

describe('shiftLabel', () => {
  it('signs day shifts', () => {
    expect(shiftLabel(3)).toBe('+3 d')
    expect(shiftLabel(-2)).toBe('-2 d')
    expect(shiftLabel(0)).toBe('')
    expect(shiftLabel(null)).toBe('')
  })
})
