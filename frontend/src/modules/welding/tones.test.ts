import { describe, expect, it } from 'vitest'
import { dueTone } from '../calibration/api'
import { stateTone } from './api'

describe('register colouring', () => {
  it('colours qualification states', () => {
    expect(stateTone('valid')).toContain('green')
    expect(stateTone('expiring')).toContain('amber')
    expect(stateTone('lapsed')).toContain('red')
    expect(stateTone(undefined)).toBe('text-muted-foreground')
  })

  it('colours calibration due and overdue rows', () => {
    expect(dueTone('overdue')).toContain('red')
    expect(dueTone('due')).toContain('amber')
    expect(dueTone('in_service')).toBe('')
  })
})
