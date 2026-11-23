import { describe, expect, it } from 'vitest'
import type { Activity } from './api'
import { COLORS, barColor, floatOf, isCritical } from './gantt-colors'

const base = {
  type: 'task',
  status: 'pending',
  is_critical: false,
  total_float: 5,
  p6_critical: null,
  p6_float_days: null,
} as unknown as Activity

describe('P6 float and critical', () => {
  it('uses the CPM for activities not mirrored from P6', () => {
    expect(isCritical(base)).toBe(false)
    expect(floatOf(base)).toBe(5)
    expect(barColor(base)).toBe(COLORS.pending)
  })

  it('prefers what P6 reports for a mirrored activity', () => {
    const p6 = { ...base, p6_critical: true, p6_float_days: 0 } as Activity
    expect(isCritical(p6)).toBe(true)
    expect(floatOf(p6)).toBe(0)
    expect(barColor(p6)).toBe(COLORS.critical)
    const notCritical = {
      ...base,
      is_critical: true,
      p6_critical: false,
      p6_float_days: 2.5,
    } as Activity
    expect(isCritical(notCritical)).toBe(false)
    expect(floatOf(notCritical)).toBe(2.5)
  })
})
