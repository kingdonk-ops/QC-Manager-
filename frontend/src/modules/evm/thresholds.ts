/**
 * Red / amber / green for performance indices: below 0.9 red, 0.9 to 0.98 amber, 0.98 and up green.
 *
 * SPI and CPI are read directly. TCPI is the efficiency still needed, so a higher value is worse:
 * it is judged by its inverse. EAC and VAC are judged by BAC / EAC (the CPI the forecast implies).
 */
export type Tone = 'good' | 'warn' | 'bad' | 'none'

export const RED_BELOW = 0.9
export const GREEN_FROM = 0.98

export function indexTone(value: number | null | undefined): Tone {
  if (value === null || value === undefined || !Number.isFinite(value))
    return 'none'
  if (value < RED_BELOW) return 'bad'
  if (value < GREEN_FROM) return 'warn'
  return 'good'
}

export function tcpiTone(tcpi: number | null | undefined): Tone {
  if (tcpi === null || tcpi === undefined) return 'none'
  if (tcpi <= 0) return 'good'
  return indexTone(1 / tcpi)
}

export function forecastTone(
  bac: number | null | undefined,
  eac: number | null | undefined
): Tone {
  if (!bac || !eac) return 'none'
  return indexTone(bac / eac)
}

export const toneText: Record<Tone, string> = {
  good: 'text-green-600 dark:text-green-500',
  warn: 'text-amber-600 dark:text-amber-500',
  bad: 'text-red-600 dark:text-red-500',
  none: 'text-muted-foreground',
}

export const toneBorder: Record<Tone, string> = {
  good: 'border-l-green-600',
  warn: 'border-l-amber-500',
  bad: 'border-l-red-600',
  none: 'border-l-border',
}

export function formatIndex(value: number | null | undefined) {
  return value === null || value === undefined ? '—' : value.toFixed(2)
}

export function formatAmount(
  value: number | null | undefined,
  basis: 'hours' | 'cost',
  currency = 'AUD'
) {
  if (value === null || value === undefined) return '—'
  if (basis === 'cost')
    return new Intl.NumberFormat(undefined, {
      style: 'currency',
      currency,
      maximumFractionDigits: 0,
    }).format(value)
  return `${new Intl.NumberFormat(undefined, { maximumFractionDigits: 0 }).format(value)} h`
}
