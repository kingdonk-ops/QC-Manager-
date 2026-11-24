import { describe, expect, it } from 'vitest'
import {
  attachmentPairValid,
  authoritySatisfies,
  canSubmitWaiver,
  defaultBlocking,
  gateActions,
  isWaivable,
  lightTone,
} from './gate-rules'

describe('isWaivable', () => {
  it('allows witness, surveillance and review but never hold', () => {
    expect(isWaivable('witness')).toBe(true)
    expect(isWaivable('surveillance')).toBe(true)
    expect(isWaivable('review')).toBe(true)
    expect(isWaivable('hold')).toBe(false)
  })
})

describe('defaultBlocking', () => {
  it('blocks by default only for a hold', () => {
    expect(defaultBlocking('hold')).toBe(true)
    expect(['witness', 'surveillance', 'review'].some(defaultBlocking)).toBe(
      false
    )
  })
})

describe('authoritySatisfies', () => {
  it('needs an equal or higher level', () => {
    expect(
      authoritySatisfies('contractor_qc', 'authority_having_jurisdiction')
    ).toBe(false)
    expect(
      authoritySatisfies('authority_having_jurisdiction', 'contractor_qa')
    ).toBe(true)
    expect(authoritySatisfies('contractor_qa', 'third_party_inspector')).toBe(
      false
    )
    expect(
      authoritySatisfies('authority_having_jurisdiction', 'third_party_inspector')
    ).toBe(true)
    expect(authoritySatisfies('client', 'client')).toBe(true)
  })
})

describe('attachmentPairValid', () => {
  it('needs both the kind and the identifier or neither', () => {
    expect(attachmentPairValid('node', '')).toBe(false)
    expect(attachmentPairValid('', '5')).toBe(false)
    expect(attachmentPairValid('node', 5)).toBe(true)
    expect(attachmentPairValid('', '')).toBe(true)
    expect(attachmentPairValid(null, null)).toBe(true)
  })
})

describe('gateActions', () => {
  const perms = { approve: true, delete: true }

  it('offers waive on every non-hold kind and never on a hold', () => {
    for (const kind of ['witness', 'surveillance', 'review'])
      expect(gateActions({ kind, status: 'pending' }, perms).waive).toBe(true)
    expect(gateActions({ kind: 'hold', status: 'pending' }, perms).waive).toBe(
      false
    )
  })

  it('offers nothing on a decided gate or without the permission', () => {
    expect(gateActions({ kind: 'witness', status: 'released' }, perms)).toEqual({
      release: false,
      waive: false,
      void: false,
      delete: false,
    })
    expect(
      gateActions(
        { kind: 'witness', status: 'pending' },
        { approve: false, delete: false }
      ).release
    ).toBe(false)
  })
})

describe('canSubmitWaiver', () => {
  it('needs a non-empty reason', () => {
    expect(canSubmitWaiver('')).toBe(false)
    expect(canSubmitWaiver('   ')).toBe(false)
    expect(canSubmitWaiver('Client agreed on site')).toBe(true)
  })
})

describe('lightTone', () => {
  it('colours the line states', () => {
    expect(lightTone('passed')).toBe(lightTone('released'))
    expect(lightTone('blocked')).toContain('red')
    expect(lightTone('pending')).toContain('amber')
    expect(lightTone('review')).not.toBe(lightTone('blocked'))
  })
})
