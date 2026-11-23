/**
 * Display and pre-validation helpers for acceptance criteria. They mirror the server's rules only to give
 * quick feedback: limits are stored as text, compared as exact decimals, and the server decides every verdict.
 */

type Dec = { n: bigint; s: number }

export const RULE_TYPES = [
  'range',
  'minimum',
  'maximum',
  'boolean',
  'free_text',
] as const

export type Limits = {
  rule_type?: string | null
  nominal?: string | null
  lower_limit?: string | null
  upper_limit?: string | null
  unit?: string | null
}

const PLAIN = /^([+-]?)(\d*)(?:\.(\d*))?$/

/** A plain decimal (optional sign and fraction, no locale formats, no unit letters), else null. */
function parseDecimal(text: string | null | undefined): Dec | null {
  const raw = (text ?? '').trim()
  const m = PLAIN.exec(raw)
  if (!m) return null
  const int = m[2] ?? ''
  const frac = m[3] ?? ''
  if (!int && !frac) return null
  const n = BigInt(`${int}${frac}` || '0')
  return { n: m[1] === '-' ? -n : n, s: frac.length }
}

function align(a: Dec, b: Dec): [bigint, bigint, number] {
  const s = Math.max(a.s, b.s)
  return [
    a.n * 10n ** BigInt(s - a.s),
    b.n * 10n ** BigInt(s - b.s),
    s,
  ]
}

function format(n: bigint, s: number): string {
  const neg = n < 0n
  const abs = (neg ? -n : n).toString().padStart(s + 1, '0')
  const int = abs.slice(0, abs.length - s)
  const frac = abs.slice(abs.length - s).replace(/0+$/, '')
  const sign = neg && (int !== '0' || frac) ? '-' : ''
  return `${sign}${int}${frac ? `.${frac}` : ''}`
}

export function isDecimal(text: string | null | undefined): boolean {
  return parseDecimal(text) !== null
}

export function isNumericRule(rule: string | null | undefined): boolean {
  return rule === 'range' || rule === 'minimum' || rule === 'maximum'
}

const filled = (v: string | null | undefined) => (v ?? '').trim() !== ''

/** The swap message when a range rule has two numeric limits in the wrong order, else null. */
export function rangeOrderError(
  rule: string | null | undefined,
  lower: string | null | undefined,
  upper: string | null | undefined
): string | null {
  if (rule !== 'range') return null
  const lo = parseDecimal(lower)
  const hi = parseDecimal(upper)
  if (!lo || !hi) return null
  const [a, b] = align(lo, hi)
  return a > b
    ? 'The lower limit is above the upper limit. Swap them.'
    : null
}

/** True when a limit the rule uses is filled in but is not a plain number (results will be not assessed). */
export function nonNumericWarning(
  rule: string | null | undefined,
  lower: string | null | undefined,
  upper: string | null | undefined
): boolean {
  if (!isNumericRule(rule)) return false
  const used: (string | null | undefined)[] =
    rule === 'range' ? [lower, upper] : rule === 'minimum' ? [lower] : [upper]
  return used.some((v) => filled(v) && !isDecimal(v))
}

/** Absolute limits from a nominal and its deviations, in exact decimal arithmetic; null when not numeric. */
export function deviationLimits(
  nominal: string,
  minus: string,
  plus: string
): { lower: string; upper: string } | null {
  const nom = parseDecimal(nominal)
  const lo = filled(minus) ? parseDecimal(minus) : { n: 0n, s: 0 }
  const hi = filled(plus) ? parseDecimal(plus) : { n: 0n, s: 0 }
  if (!nom || !lo || !hi) return null
  const [n1, d1, s1] = align(nom, lo)
  const [n2, d2, s2] = align(nom, hi)
  return { lower: format(n1 - d1, s1), upper: format(n2 + d2, s2) }
}

/** Nominal, inclusive lower and inclusive upper, each only when non-empty (a zero limit is shown). */
export function toleranceParts(c: Limits): { kind: string; value: string }[] {
  const parts: { kind: string; value: string }[] = []
  if (filled(c.nominal))
    parts.push({ kind: 'nominal', value: (c.nominal as string).trim() })
  if (filled(c.lower_limit))
    parts.push({ kind: 'lower', value: (c.lower_limit as string).trim() })
  if (filled(c.upper_limit))
    parts.push({ kind: 'upper', value: (c.upper_limit as string).trim() })
  return parts
}

export function toleranceDisplay(
  c: Limits,
  labels: { nominal: string; lower: string; upper: string } = {
    nominal: 'Nominal',
    lower: '≥',
    upper: '≤',
  }
): string {
  const unit = filled(c.unit) ? ` ${(c.unit as string).trim()}` : ''
  const text = toleranceParts(c)
    .map((p) =>
      p.kind === 'nominal'
        ? `${labels.nominal} ${p.value}`
        : `${p.kind === 'lower' ? labels.lower : labels.upper} ${p.value}`
    )
    .join(' · ')
  return text ? `${text}${unit}` : ''
}

/** Numeric limits and unit an item takes from a criterion (a rule that is not numeric leaves them open). */
export function itemLimits(c: Limits): {
  min_value: number | null
  max_value: number | null
  unit: string | null
} {
  const num = (v: string | null | undefined) =>
    isDecimal(v) ? Number((v as string).trim()) : null
  const rule = c.rule_type
  return {
    min_value: rule === 'range' || rule === 'minimum' ? num(c.lower_limit) : null,
    max_value: rule === 'range' || rule === 'maximum' ? num(c.upper_limit) : null,
    unit: filled(c.unit) ? (c.unit as string).trim() : null,
  }
}
