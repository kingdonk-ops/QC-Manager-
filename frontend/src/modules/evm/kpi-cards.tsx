import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import type { Basis, Metrics } from './api'
import {
  forecastTone,
  formatAmount,
  formatIndex,
  indexTone,
  tcpiTone,
  toneBorder,
  toneText,
  type Tone,
} from './thresholds'

function Kpi({
  label,
  value,
  hint,
  tone = 'none',
}: {
  label: string
  value: string
  hint?: string
  tone?: Tone
}) {
  return (
    <Card
      className={cn('gap-1 border-l-4 py-3', toneBorder[tone])}
      data-tone={tone}
    >
      <CardHeader className='px-4'>
        <CardTitle className='text-xs font-medium text-muted-foreground'>
          {label}
        </CardTitle>
      </CardHeader>
      <CardContent className='px-4'>
        <p
          className={cn(
            'text-xl font-semibold tabular-nums',
            tone !== 'none' && toneText[tone]
          )}
        >
          {value}
        </p>
        {hint ? (
          <p className='text-xs text-muted-foreground tabular-nums'>{hint}</p>
        ) : null}
      </CardContent>
    </Card>
  )
}

export function KpiCards({
  total,
  basis,
  currency,
}: {
  total: Metrics
  basis: Basis
  currency: string
}) {
  const { t } = useTranslation()
  const amount = (v: number | null | undefined) =>
    formatAmount(v, basis, currency)
  const pct = (v: number | null | undefined) =>
    v === null || v === undefined ? '—' : `${v.toFixed(1)}%`
  const eacTone = forecastTone(total.bac, total.eac)

  return (
    <div className='grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6'>
      <Kpi
        label={t('evm.spi')}
        value={formatIndex(total.spi)}
        hint={`${t('evm.sv')} ${amount(total.sv)}`}
        tone={indexTone(total.spi)}
      />
      <Kpi
        label={t('evm.cpi')}
        value={formatIndex(total.cpi)}
        hint={`${t('evm.cv')} ${amount(total.cv)}`}
        tone={indexTone(total.cpi)}
      />
      <Kpi
        label={t('evm.eac')}
        value={amount(total.eac)}
        hint={`${t('evm.bac')} ${amount(total.bac)}`}
        tone={eacTone}
      />
      <Kpi
        label={t('evm.vac')}
        value={amount(total.vac)}
        hint={`${t('evm.etc')} ${amount(total.etc)}`}
        tone={eacTone}
      />
      <Kpi
        label={t('evm.tcpi')}
        value={formatIndex(total.tcpi)}
        hint={`${t('evm.tcpi_eac')} ${formatIndex(total.tcpi_eac)}`}
        tone={tcpiTone(total.tcpi)}
      />
      <Kpi
        label={t('evm.progress')}
        value={pct(total.percent_complete)}
        hint={`${t('evm.planned')} ${pct(total.percent_planned)} · ${t('evm.productivity')} ${formatIndex(total.productivity)}`}
      />
    </div>
  )
}
