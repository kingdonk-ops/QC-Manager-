import { describe, expect, it } from 'vitest'
import {
  forecastTone,
  formatAmount,
  formatIndex,
  indexTone,
  tcpiTone,
} from './thresholds'

describe('indexTone', () => {
  it('is red below 0.9, amber to 0.98, green from 0.98', () => {
    expect(indexTone(0.5)).toBe('bad')
    expect(indexTone(0.8999)).toBe('bad')
    expect(indexTone(0.9)).toBe('warn')
    expect(indexTone(0.979)).toBe('warn')
    expect(indexTone(0.98)).toBe('good')
    expect(indexTone(1.3)).toBe('good')
  })

  it('has no colour without a value', () => {
    expect(indexTone(null)).toBe('none')
    expect(indexTone(undefined)).toBe('none')
  })
})

describe('tcpiTone', () => {
  it('reads a higher TCPI as worse', () => {
    expect(tcpiTone(1.0)).toBe('good')
    expect(tcpiTone(1.05)).toBe('warn')
    expect(tcpiTone(1.2)).toBe('bad')
    expect(tcpiTone(0.8)).toBe('good')
    expect(tcpiTone(null)).toBe('none')
  })
})

describe('forecastTone', () => {
  it('compares the budget with the estimate at completion', () => {
    expect(forecastTone(1000, 1000)).toBe('good')
    expect(forecastTone(1000, 1050)).toBe('warn')
    expect(forecastTone(1000, 1200)).toBe('bad')
    expect(forecastTone(1000, null)).toBe('none')
  })
})

describe('formatting', () => {
  it('formats indices and hours', () => {
    expect(formatIndex(0.8765)).toBe('0.88')
    expect(formatIndex(null)).toBe('—')
    expect(formatAmount(1234.4, 'hours')).toMatch(/1.?234 h/)
    expect(formatAmount(null, 'hours')).toBe('—')
  })
})
