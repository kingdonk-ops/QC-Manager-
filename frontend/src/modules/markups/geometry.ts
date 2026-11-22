/**
 * Markup geometry, mirroring the backend's `markups/geometry.py`.
 *
 * Coordinates are PDF units of the page as displayed at scale 1, origin top-left, y down,
 * so they don't change with the zoom. A page's calibration is metres per PDF unit.
 */

export type Point = [number, number]
export type Box = { x: number; y: number; w: number; h: number }

export const UNIT_METERS: Record<string, number> = {
  m: 1,
  mm: 0.001,
  cm: 0.01,
  km: 1000,
  ft: 0.3048,
  in: 0.0254,
}

export const BOX_TYPES = [
  'rect',
  'ellipse',
  'cloud',
  'highlight',
  'stamp',
  'text',
  'callout',
] as const
export const TWO_POINT_TYPES = ['line', 'arrow', 'measure_length'] as const
export const PATH_TYPES = [
  'polyline',
  'freehand',
  'measure_polyline',
  'measure_area',
] as const
export const MEASURE_TYPES = [
  'measure_length',
  'measure_polyline',
  'measure_area',
] as const

export function distance(a: Point, b: Point) {
  return Math.hypot(b[0] - a[0], b[1] - a[1])
}

export function polylineLength(points: Point[]) {
  let total = 0
  for (let i = 0; i < points.length - 1; i++)
    total += distance(points[i], points[i + 1])
  return total
}

/** The shoelace formula; the polygon closes itself. */
export function polygonArea(points: Point[]) {
  if (points.length < 3) return 0
  let twice = 0
  for (let i = 0; i < points.length; i++) {
    const [x1, y1] = points[i]
    const [x2, y2] = points[(i + 1) % points.length]
    twice += x1 * y2 - x2 * y1
  }
  return Math.abs(twice) / 2
}

/** Metres per PDF unit from two picked points and the real distance between them. */
export function scaleFactor(
  p1: Point,
  p2: Point,
  realDistance: number,
  unit: string
) {
  const picked = distance(p1, p2)
  if (!(unit in UNIT_METERS)) throw new Error(`Unknown unit ${unit}`)
  if (!(realDistance > 0))
    throw new Error('The real distance must be more than zero.')
  if (picked <= 0) throw new Error('Pick two different points.')
  return (realDistance * UNIT_METERS[unit]) / picked
}

export type Measurement = { value: number; unit: 'm' | 'm2' }

export function measure(
  type: string,
  points: Point[],
  metersPerUnit: number
): Measurement {
  if (type === 'measure_area')
    return { value: polygonArea(points) * metersPerUnit ** 2, unit: 'm2' }
  return { value: polylineLength(points) * metersPerUnit, unit: 'm' }
}

export function formatMeasurement(m?: { value: number; unit: string } | null) {
  if (!m) return ''
  const fixed = (v: number, d: number) =>
    v.toLocaleString('en-US', {
      minimumFractionDigits: d,
      maximumFractionDigits: d,
    })
  if (m.unit === 'm2') return `${fixed(m.value, 2)} m²`
  return m.value < 10 ? `${fixed(m.value, 3)} m` : `${fixed(m.value, 2)} m`
}

export function normaliseBox(a: Point, b: Point): Box {
  return {
    x: Math.min(a[0], b[0]),
    y: Math.min(a[1], b[1]),
    w: Math.abs(b[0] - a[0]),
    h: Math.abs(b[1] - a[1]),
  }
}

/** Bumps of a revision cloud round a box, as an SVG path (semicircles bulging outwards). */
export function cloudPath({ x, y, w, h }: Box) {
  const size = Math.max(
    6,
    Math.min(24, Math.min(w, h) > 0 ? Math.min(w, h) / 4 : 6)
  )
  const corners: Point[] = [
    [x, y],
    [x + w, y],
    [x + w, y + h],
    [x, y + h],
  ]
  let d = `M ${x} ${y}`
  for (let i = 0; i < 4; i++) {
    const a = corners[i]
    const b = corners[(i + 1) % 4]
    const length = distance(a, b)
    if (length === 0) continue
    const bumps = Math.max(1, Math.round(length / size))
    const step = length / bumps
    for (let k = 1; k <= bumps; k++) {
      const px = a[0] + ((b[0] - a[0]) * k) / bumps
      const py = a[1] + ((b[1] - a[1]) * k) / bumps
      d += ` A ${step / 2} ${step / 2} 0 0 1 ${px} ${py}`
    }
  }
  return `${d} Z`
}

export function centroid(points: Point[]): Point {
  const n = points.length || 1
  return [
    points.reduce((s, p) => s + p[0], 0) / n,
    points.reduce((s, p) => s + p[1], 0) / n,
  ]
}

/** Move a geometry by (dx, dy). */
export function translate<G extends Record<string, unknown>>(
  geometry: G,
  dx: number,
  dy: number
): G {
  const out: Record<string, unknown> = { ...geometry }
  if (typeof out.x === 'number') out.x = (out.x as number) + dx
  if (typeof out.y === 'number') out.y = (out.y as number) + dy
  if (Array.isArray(out.anchor)) {
    const [ax, ay] = out.anchor as Point
    out.anchor = [ax + dx, ay + dy]
  }
  if (Array.isArray(out.points))
    out.points = (out.points as Point[]).map(([px, py]) => [px + dx, py + dy])
  return out as G
}

/** Bounding box of any geometry, for hit-testing and the selection outline. */
export function bounds(geometry: Record<string, unknown>): Box {
  if (Array.isArray(geometry.points)) {
    const pts = geometry.points as Point[]
    const xs = pts.map((p) => p[0])
    const ys = pts.map((p) => p[1])
    const box = {
      x: Math.min(...xs),
      y: Math.min(...ys),
      w: Math.max(...xs) - Math.min(...xs),
      h: Math.max(...ys) - Math.min(...ys),
    }
    return box
  }
  const box = geometry as unknown as Box
  if (Array.isArray(geometry.anchor)) {
    const [ax, ay] = geometry.anchor as Point
    const x = Math.min(box.x, ax)
    const y = Math.min(box.y, ay)
    return {
      x,
      y,
      w: Math.max(box.x + box.w, ax) - x,
      h: Math.max(box.y + box.h, ay) - y,
    }
  }
  return box
}
