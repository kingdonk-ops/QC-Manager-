import { AlertCircle, AlertTriangle, Info } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { type Ruleset, useValidation } from './api'
import { RULESETS, scoreTone } from './format'

const SEVERITY = {
  error: { icon: AlertCircle, tone: 'text-red-600 dark:text-red-400' },
  warning: { icon: AlertTriangle, tone: 'text-amber-600 dark:text-amber-400' },
  info: { icon: Info, tone: 'text-blue-600 dark:text-blue-400' },
} as const

/** A rule set's score and findings; clicking a finding shows its row. */
export function ValidationPanel({
  boqId,
  ruleset,
  onRuleset,
  onFinding,
}: {
  boqId: number
  ruleset: Ruleset
  onRuleset: (ruleset: Ruleset) => void
  onFinding: (positionId: number) => void
}) {
  const { t } = useTranslation()
  const { data: report, isFetching } = useValidation(boqId, ruleset)
  return (
    <Card className='gap-2 py-3'>
      <CardHeader className='flex flex-row items-center justify-between gap-2 px-4'>
        <CardTitle className='text-sm'>{t('boq.validation')}</CardTitle>
        <Select value={ruleset} onValueChange={(v) => onRuleset(v as Ruleset)}>
          <SelectTrigger className='h-7 w-40' size='sm'>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {RULESETS.map((r) => (
              <SelectItem key={r} value={r}>
                {t(`boq.ruleset.${r}`)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </CardHeader>
      <CardContent className='grid gap-2 px-4'>
        {report ? (
          <>
            <div className='flex items-baseline gap-3'>
              <span
                className={cn(
                  'text-3xl font-semibold tabular-nums',
                  scoreTone(report.score),
                  isFetching && 'opacity-50'
                )}
                data-testid='boq-score'
              >
                {report.score}%
              </span>
              <span className='text-xs text-muted-foreground'>
                {t('boq.score')}
              </span>
            </div>
            <div className='flex gap-3 text-xs'>
              <span className={SEVERITY.error.tone}>✕ {report.errors}</span>
              <span className={SEVERITY.warning.tone}>! {report.warnings}</span>
              <span className={SEVERITY.info.tone}>i {report.infos}</span>
            </div>
            {report.findings.length === 0 ? (
              <p className='text-sm text-muted-foreground'>
                {t('boq.no_findings')}
              </p>
            ) : (
              <ul className='max-h-[50vh] overflow-auto text-xs'>
                {report.findings.map((f, i) => {
                  const { icon: Icon, tone } = SEVERITY[f.severity]
                  return (
                    <li key={`${f.rule_id}-${f.position_id}-${i}`}>
                      <button
                        type='button'
                        disabled={f.position_id === null}
                        onClick={() =>
                          f.position_id !== null && onFinding(f.position_id)
                        }
                        className='flex w-full items-start gap-2 rounded px-1 py-1 text-start enabled:hover:bg-accent'
                      >
                        <Icon
                          className={cn('mt-0.5 size-3.5 shrink-0', tone)}
                        />
                        <span>
                          <span className='font-mono text-muted-foreground'>
                            {f.rule_id}
                          </span>{' '}
                          {f.message}
                        </span>
                      </button>
                    </li>
                  )
                })}
              </ul>
            )}
          </>
        ) : null}
      </CardContent>
    </Card>
  )
}
