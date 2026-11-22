import { describe, expect, it } from 'vitest'
import { reorder, toLocalInput } from './format'

describe('reorder', () => {
  it('moves an agenda item before another, or to the end', () => {
    expect(reorder([1, 2, 3], 3, 1)).toEqual([3, 1, 2])
    expect(reorder([1, 2, 3], 1, null)).toEqual([2, 3, 1])
    expect(reorder([1, 2, 3], 1, 3)).toEqual([2, 1, 3])
  })
})

describe('toLocalInput', () => {
  it('gives a datetime-local value in local time', () => {
    const d = new Date(2026, 2, 9, 7, 5)
    expect(toLocalInput(d.toISOString())).toBe('2026-03-09T07:05')
  })
})
