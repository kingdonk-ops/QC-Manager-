import { describe, expect, it } from 'vitest'
import {
  bounds,
  cloudPath,
  formatMeasurement,
  measure,
  normaliseBox,
  polygonArea,
  scaleFactor,
  translate,
  type Point,
} from './geometry'

describe('calibration', () => {
  it('gives metres per PDF unit', () => {
    expect(scaleFactor([100, 100], [300, 100], 5, 'm')).toBeCloseTo(0.025)
    expect(scaleFactor([0, 0], [0, 200], 5000, 'mm')).toBeCloseTo(0.025)
    expect(scaleFactor([0, 0], [120, 160], 10, 'ft')).toBeCloseTo(
      (10 * 0.3048) / 200
    )
  })

  it('refuses a zero distance or the same point twice', () => {
    expect(() => scaleFactor([1, 1], [1, 1], 5, 'm')).toThrow()
    expect(() => scaleFactor([0, 0], [1, 0], 0, 'm')).toThrow()
  })
})

describe('measurements', () => {
  const square: Point[] = [
    [0, 0],
    [200, 0],
    [200, 200],
    [0, 200],
  ]

  it('scales lengths by the factor', () => {
    expect(
      measure(
        'measure_length',
        [
          [0, 0],
          [300, 400],
        ],
        0.025
      ).value
    ).toBeCloseTo(12.5)
    expect(measure('measure_polyline', square, 0.025).value).toBeCloseTo(15)
  })

  it('scales areas by the square of the factor', () => {
    const area = measure('measure_area', square, 0.025)
    expect(area.unit).toBe('m2')
    expect(area.value).toBeCloseTo(25)
    expect(polygonArea([...square].reverse())).toBe(40000)
  })

  it('formats like the printed PDF', () => {
    expect(formatMeasurement({ value: 2.5, unit: 'm' })).toBe('2.500 m')
    expect(formatMeasurement({ value: 1234.567, unit: 'm' })).toBe('1,234.57 m')
    expect(formatMeasurement({ value: 25, unit: 'm2' })).toBe('25.00 m²')
  })
})

describe('shapes', () => {
  it('normalises a dragged box', () => {
    expect(normaliseBox([50, 60], [30, 70])).toEqual({
      x: 30,
      y: 60,
      w: 20,
      h: 10,
    })
  })

  it('moves points, boxes and anchors', () => {
    expect(
      translate(
        {
          points: [
            [0, 0],
            [1, 1],
          ],
        },
        5,
        5
      )
    ).toEqual({
      points: [
        [5, 5],
        [6, 6],
      ],
    })
    expect(translate({ x: 1, y: 2, w: 3, h: 4, anchor: [0, 0] }, 1, 1)).toEqual(
      {
        x: 2,
        y: 3,
        w: 3,
        h: 4,
        anchor: [1, 1],
      }
    )
    expect(bounds({ x: 10, y: 10, w: 10, h: 10, anchor: [0, 30] })).toEqual({
      x: 0,
      y: 10,
      w: 20,
      h: 20,
    })
  })

  it('draws a closed cloud', () => {
    const d = cloudPath({ x: 0, y: 0, w: 100, h: 50 })
    expect(d.startsWith('M 0 0')).toBe(true)
    expect(d.endsWith('Z')).toBe(true)
    expect(d.split(' A ').length - 1).toBeGreaterThan(8)
  })
})
