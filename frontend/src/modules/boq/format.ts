/** Formatting and constants the BOQ screens share. */
import type { Ruleset } from './api'

export const LINE_HEIGHT = 30
/** The detail row's height for a position with `lines` resource lines. */
export const detailHeight = (lines: number) =>
  20 + 40 + LINE_HEIGHT * (Math.max(lines, 1) + 1)

export const fmt = (v: string | number | null | undefined, digits = 2) =>
  v === null || v === undefined || v === ''
    ? ''
    : Number(v).toLocaleString(undefined, {
        minimumFractionDigits: digits,
        maximumFractionDigits: Math.max(digits, 4),
      })

export const RULESETS: Ruleset[] = [
  'boq_quality',
  'din276',
  'nrm',
  'masterformat',
]

export function scoreTone(score: number) {
  if (score >= 90) return 'text-green-600 dark:text-green-400'
  if (score >= 70) return 'text-amber-600 dark:text-amber-400'
  return 'text-red-600 dark:text-red-400'
}
