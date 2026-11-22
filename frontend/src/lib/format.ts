import type { ValueFormatterParams } from 'ag-grid-community'

/** Formats money for a right-aligned grid column; pair with `type: 'rightAligned'`. */
export function money(currency = 'AUD') {
  const format = new Intl.NumberFormat(undefined, {
    style: 'currency',
    currency,
    maximumFractionDigits: 0,
  })
  return (params: Pick<ValueFormatterParams, 'value'>) =>
    params.value === null || params.value === undefined || params.value === ''
      ? ''
      : format.format(Number(params.value))
}
