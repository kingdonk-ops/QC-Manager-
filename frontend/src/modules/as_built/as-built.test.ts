import { describe, expect, it } from 'vitest'
import {
  allowedActions,
  digestPrefix,
  isEditable,
  statusActions,
  toleranceTone,
} from './as-built'

const names = (status: string) =>
  Object.entries(statusActions(status))
    .filter(([, on]) => on)
    .map(([name]) => name)

describe('statusActions', () => {
  it('offers survey on a draft', () => {
    expect(names('draft')).toEqual(['survey'])
  })

  it('offers survey and verify once surveyed', () => {
    expect(names('surveyed')).toEqual(['survey', 'verify'])
  })

  it('offers sign on a verified record', () => {
    expect(names('verified')).toEqual(['sign'])
  })

  it('offers nothing on a recorded, superseded or void record', () => {
    expect(names('recorded')).toEqual([])
    expect(names('superseded')).toEqual([])
    expect(names('void')).toEqual([])
  })
})

describe('allowedActions', () => {
  it('needs update to survey, review to verify and approve to sign', () => {
    const none = { update: false, review: false, approve: false }
    expect(allowedActions('surveyed', none)).toEqual({
      survey: false,
      verify: false,
      sign: false,
    })
    expect(allowedActions('surveyed', { ...none, review: true })).toEqual({
      survey: false,
      verify: true,
      sign: false,
    })
    expect(allowedActions('verified', { ...none, approve: true }).sign).toBe(
      true
    )
  })
})

describe('isEditable', () => {
  it('offers no edit once the record is recorded', () => {
    expect(isEditable('draft')).toBe(true)
    expect(isEditable('surveyed')).toBe(true)
    expect(isEditable('recorded')).toBe(false)
  })
})

describe('toleranceTone', () => {
  it('shows within, out of tolerance and not assessed differently', () => {
    const tones = new Set([
      toleranceTone('within'),
      toleranceTone('out_of_tolerance'),
      toleranceTone('not_assessed'),
    ])
    expect(tones.size).toBe(3)
    expect(toleranceTone(null)).toBe(toleranceTone('not_assessed'))
  })
})

describe('digestPrefix', () => {
  it('shortens a digest and shows nothing when there is none', () => {
    expect(digestPrefix('a'.repeat(64))).toBe(`${'a'.repeat(12)}…`)
    expect(digestPrefix(null)).toBe('')
  })
})
