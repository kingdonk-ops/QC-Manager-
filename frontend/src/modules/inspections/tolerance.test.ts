import { describe, expect, it } from 'vitest'
import {
  deviationLimits,
  itemLimits,
  nonNumericWarning,
  rangeOrderError,
  toleranceDisplay,
} from './tolerance'

describe('rangeOrderError', () => {
  it('asks for a swap when a range is back to front', () => {
    expect(rangeOrderError('range', '20', '10')).toMatch(/swap/i)
  })

  it('accepts equal limits and ignores other rules', () => {
    expect(rangeOrderError('range', '15', '15')).toBeNull()
    expect(rangeOrderError('minimum', '20', '10')).toBeNull()
    expect(rangeOrderError('maximum', '20', '10')).toBeNull()
  })

  it('leaves non-numeric or partial limits untouched', () => {
    expect(rangeOrderError('range', 'abc', '5')).toBeNull()
    expect(rangeOrderError('range', '', '5')).toBeNull()
  })

  it('compares decimals exactly', () => {
    expect(rangeOrderError('range', '-2.5', '-2.50')).toBeNull()
    expect(rangeOrderError('range', '0.30', '0.3')).toBeNull()
    expect(rangeOrderError('range', '0.31', '0.3')).not.toBeNull()
  })
})

describe('nonNumericWarning', () => {
  it('warns only for a filled limit the rule uses that is not a number', () => {
    expect(nonNumericWarning('range', 'abc', '5')).toBe(true)
    expect(nonNumericWarning('minimum', '15 mm', null)).toBe(true)
    expect(nonNumericWarning('maximum', 'abc', '5')).toBe(false)
    expect(nonNumericWarning('range', '1', '5')).toBe(false)
    expect(nonNumericWarning('free_text', 'abc', 'def')).toBe(false)
  })
})

describe('deviationLimits', () => {
  it('fills absolute limits from nominal and deviations', () => {
    expect(deviationLimits('50', '0', '5')).toEqual({
      lower: '50',
      upper: '55',
    })
  })

  it('does exact decimal arithmetic', () => {
    expect(deviationLimits('1.1', '0.2', '0.2')).toEqual({
      lower: '0.9',
      upper: '1.3',
    })
  })

  it('handles negatives and empty deviations', () => {
    expect(deviationLimits('-1', '2', '')).toEqual({
      lower: '-3',
      upper: '-1',
    })
  })

  it('gives nothing for a non-numeric nominal', () => {
    expect(deviationLimits('abc', '1', '1')).toBeNull()
  })
})

describe('toleranceDisplay', () => {
  it('shows a zero upper bound and omits the empty lower bound', () => {
    const text = toleranceDisplay({
      rule_type: 'maximum',
      nominal: null,
      lower_limit: '',
      upper_limit: '0',
      unit: null,
    })
    expect(text).toContain('≤ 0')
    expect(text).not.toContain('≥')
  })

  it('shows nominal, both bounds and unit', () => {
    expect(
      toleranceDisplay({
        nominal: '50',
        lower_limit: '48',
        upper_limit: '55',
        unit: 'mm',
      })
    ).toBe('Nominal 50 · ≥ 48 · ≤ 55 mm')
  })

  it('is empty with no limits', () => {
    expect(toleranceDisplay({ unit: 'mm' })).toBe('')
  })
})

describe('itemLimits', () => {
  it('copies the numeric limits the rule uses', () => {
    expect(
      itemLimits({
        rule_type: 'range',
        lower_limit: '50',
        upper_limit: '55',
        unit: 'mm',
      })
    ).toEqual({ min_value: 50, max_value: 55, unit: 'mm' })
    expect(
      itemLimits({ rule_type: 'minimum', lower_limit: '355', upper_limit: '9' })
    ).toEqual({ min_value: 355, max_value: null, unit: null })
  })

  it('leaves the limits open for a free-text rule', () => {
    expect(
      itemLimits({ rule_type: 'free_text', lower_limit: '1', upper_limit: '2' })
    ).toEqual({ min_value: null, max_value: null, unit: null })
  })
})
