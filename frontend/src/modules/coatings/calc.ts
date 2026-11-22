/**
 * Live feedback while readings are typed. Mirrors `backend/src/modules/coatings/calc.py`; the server's
 * verdict is the one stored.
 */

export type DftRule = '80/20' | '90/10' | 'min_max'

export const RULES: DftRule[] = ['80/20', '90/10', 'min_max']

/** rule -> [share of readings allowed below the minimum, lowest reading as a fraction of the minimum] */
const LIMITS: Record<DftRule, [number, number]> = {
  '80/20': [0.2, 0.8],
  '90/10': [0.1, 0.9],
  min_max: [0, 1],
}

const round1 = (n: number) => Math.round(n * 10) / 10

/** Dew point by the Magnus formula (Sonntag constants). */
export function dewPoint(airC: number, rhPct: number) {
  const b = 17.62
  const c = 243.12
  const gamma = Math.log(rhPct / 100) + (b * airC) / (c + airC)
  return round1((c * gamma) / (b - gamma))
}

export function environmentCheck(
  surfaceC: number,
  dewC: number,
  requiredMargin = 3
) {
  const margin = round1(surfaceC - dewC)
  return { dewPoint: dewC, margin, passed: margin >= requiredMargin }
}

/** Readings typed as "62 70, 81\n75": any separator. */
export function parseReadings(text: string) {
  return text
    .split(/[\s,;]+/)
    .map((v) => v.trim())
    .filter(Boolean)
    .map(Number)
    .filter((n) => Number.isFinite(n) && n >= 0)
}

export type DftStats = {
  count: number
  mean: number
  minimum: number
  maximum: number
  pctWithin: number
  pctBelowMin: number
  passed: boolean
  failures: string[]
}

export function dftStats(
  readings: number[],
  dftMin: number,
  dftMax: number | null,
  rule: DftRule
): DftStats | null {
  if (!readings.length) return null
  const [allowance, floor] = LIMITS[rule]
  const n = readings.length
  const mean = readings.reduce((a, b) => a + b, 0) / n
  const low = Math.min(...readings)
  const high = Math.max(...readings)
  const below = readings.filter((r) => r < dftMin).length
  const within = readings.filter(
    (r) => r >= dftMin && (dftMax == null || r <= dftMax)
  ).length
  const failures: string[] = []
  if (mean < dftMin)
    failures.push(
      `mean ${mean.toFixed(1)} µm is below the minimum ${dftMin} µm`
    )
  if (below / n > allowance + 1e-9)
    failures.push(
      `${below} of ${n} readings below the minimum (allowed ${Math.round(allowance * 100)}%)`
    )
  if (low < floor * dftMin - 1e-9)
    failures.push(
      `lowest reading ${low} µm is below ${Math.round(floor * 100)}% of the minimum`
    )
  if (dftMax != null && high > dftMax + 1e-9)
    failures.push(
      `highest reading ${high} µm is above the maximum ${dftMax} µm`
    )
  return {
    count: n,
    mean: round1(mean),
    minimum: low,
    maximum: high,
    pctWithin: round1((100 * within) / n),
    pctBelowMin: round1((100 * below) / n),
    passed: failures.length === 0,
    failures,
  }
}
