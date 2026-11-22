import { describe, expect, it } from 'vitest'
import { dewPoint, dftStats, environmentCheck, parseReadings } from './calc'

const SET = [60, 70, 80, 90, 100, 55, 58, 62, 75, 85]

describe('coating checks (mirror of the server)', () => {
  it('finds the dew point and holds coating within 3 °C of it', () => {
    expect(dewPoint(20, 50)).toBe(9.3)
    expect(environmentCheck(12.2, 9.3).passed).toBe(false)
    expect(environmentCheck(12.3, 9.3)).toEqual({
      dewPoint: 9.3,
      margin: 3,
      passed: true,
    })
  })

  it('computes DFT statistics under each rule', () => {
    const stats = dftStats(SET, 60, 120, '80/20')
    expect(stats).toMatchObject({
      count: 10,
      mean: 73.5,
      minimum: 55,
      maximum: 100,
      pctWithin: 80,
      pctBelowMin: 20,
      passed: true,
    })
    expect(dftStats(SET, 60, 120, '90/10')?.passed).toBe(false)
    expect(dftStats([70, 80, 130], 60, 120, '80/20')?.failures).toEqual([
      'highest reading 130 µm is above the maximum 120 µm',
    ])
    expect(dftStats([], 60, 120, '80/20')).toBeNull()
  })

  it('reads numbers typed with any separator', () => {
    expect(parseReadings('62 70,81;\n75  x')).toEqual([62, 70, 81, 75])
  })
})
