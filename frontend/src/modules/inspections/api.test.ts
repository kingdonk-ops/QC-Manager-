import { describe, expect, it } from 'vitest'
import { band } from '../safety/api'
import { type InspectionItem, limitHint, readingOutcome } from './api'

const item = (min: number | null, max: number | null) =>
  ({ min_value: min, max_value: max, unit: 'mm' }) as InspectionItem

describe('readingOutcome', () => {
  it('fails readings outside the limits and passes those inside', () => {
    expect(readingOutcome(item(50, 55), 48)).toBe('fail')
    expect(readingOutcome(item(50, 55), 56)).toBe('fail')
    expect(readingOutcome(item(50, 55), 50)).toBe('pass')
    expect(readingOutcome(item(50, null), 900)).toBe('pass')
    expect(readingOutcome(item(null, 85), 86)).toBe('fail')
  })

  it('has no outcome without a reading', () => {
    expect(readingOutcome(item(50, 55), null)).toBeNull()
    expect(readingOutcome(item(50, 55), Number.NaN)).toBeNull()
  })
})

describe('limitHint', () => {
  it('describes the acceptance range', () => {
    expect(limitHint(item(50, 55))).toBe('50–55 mm')
    expect(limitHint(item(50, null))).toBe('≥ 50 mm')
    expect(limitHint(item(null, 85))).toBe('≤ 85 mm')
  })
})

describe('risk band', () => {
  it('bands severity × likelihood on the 5×5 matrix', () => {
    expect([1, 4, 5, 9, 10, 14, 15, 25].map(band)).toEqual([
      'low',
      'low',
      'medium',
      'medium',
      'high',
      'high',
      'extreme',
      'extreme',
    ])
  })
})
