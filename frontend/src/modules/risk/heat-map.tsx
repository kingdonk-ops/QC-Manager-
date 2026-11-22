import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'
import type { RiskMatrix } from './api'

function tone(score: number) {
  if (score >= 12) return 'bg-red-500/80 text-white hover:bg-red-500'
  if (score >= 8) return 'bg-orange-400/80 text-white hover:bg-orange-400'
  if (score >= 4) return 'bg-amber-300/70 text-amber-950 hover:bg-amber-300'
  return 'bg-green-500/25 text-green-900 dark:text-green-200 hover:bg-green-500/40'
}

/** Probability bands (rows, most likely on top) against impact levels (columns); click a cell to filter. */
export function HeatMap({
  matrix,
  selected,
  onSelect,
  format,
}: {
  matrix: RiskMatrix
  selected?: { band: string; impact: string }
  onSelect: (cell?: { band: string; impact: string }) => void
  format: (value: string) => string
}) {
  const { t } = useTranslation()
  const bands = [...matrix.bands].reverse()
  const cell = (band: string, impact: string) =>
    matrix.cells.find((c) => c.band === band && c.impact === impact)

  return (
    <div
      className='grid gap-1 text-xs'
      style={{
        gridTemplateColumns: `minmax(7rem, auto) repeat(${matrix.impacts.length}, minmax(0, 1fr))`,
      }}
      role='grid'
      aria-label={t('risk.heat_map')}
    >
      <div className='self-end text-muted-foreground'>
        {t('risk.probability')} ↓ / {t('risk.impact')} →
      </div>
      {matrix.impacts.map((impact) => (
        <div
          key={impact}
          className='text-center font-medium text-muted-foreground'
        >
          {t(`risk.imp.${impact}`)}
        </div>
      ))}
      {bands.map((band) => {
        const row = matrix.bands.findIndex((b) => b.key === band.key) + 1
        return [
          <div key={band.key} className='flex flex-col justify-center pe-2'>
            <span className='font-medium'>{band.label}</span>
            <span className='text-muted-foreground'>
              {band.min === band.max ? band.min : `${band.min}–${band.max}`}
            </span>
          </div>,
          ...matrix.impacts.map((impact, i) => {
            const c = cell(band.key, impact)
            const active =
              selected?.band === band.key && selected?.impact === impact
            return (
              <button
                key={`${band.key}-${impact}`}
                type='button'
                className={cn(
                  'flex h-16 flex-col items-center justify-center rounded-md transition-colors',
                  tone(row * (i + 1)),
                  active && 'ring-2 ring-primary ring-offset-2',
                  !c?.count && 'opacity-60'
                )}
                aria-pressed={active}
                onClick={() =>
                  onSelect(active ? undefined : { band: band.key, impact })
                }
              >
                <span className='text-base font-semibold tabular-nums'>
                  {c?.count ?? 0}
                </span>
                {c?.count ? (
                  <span className='tabular-nums'>{format(c.exposure)}</span>
                ) : null}
              </button>
            )
          }),
        ]
      })}
    </div>
  )
}
