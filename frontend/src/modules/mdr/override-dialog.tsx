import { useState } from 'react'
import { ShieldAlert } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { NativeSelect } from '@/components/native-select'
import {
  type Blocker,
  type GateCountsRead,
  type Override,
  SEVERITIES,
} from './override-api'

type Severity = (typeof SEVERITIES)[number]

/**
 * Override the issue blockers of a dossier: shows the blockers the server reports, takes a mandatory reason and an
 * optional severity, and after the server accepts it shows the documentation report that was raised.
 */
export function OverrideDialog({
  blockers,
  unoverridable = [],
  pending,
  error,
  result,
  onSubmit,
  onClose,
}: {
  blockers: Blocker[]
  /** Failing checks that can never be overridden: shown as the reason the override cannot be recorded. */
  unoverridable?: Blocker[]
  pending?: boolean
  error?: string | null
  result?: Override | null
  onSubmit: (body: { reason: string; severity: Severity }) => void
  onClose: () => void
}) {
  const { t } = useTranslation()
  const [reason, setReason] = useState('')
  const [touched, setTouched] = useState(false)
  const [severity, setSeverity] = useState<Severity>('major')
  const blank = reason.trim() === ''
  const refused = unoverridable.length > 0

  if (result)
    return (
      <Dialog open onOpenChange={(o) => !o && onClose()}>
        <DialogContent data-testid='override-done' className='sm:max-w-lg'>
          <DialogHeader>
            <DialogTitle>{t('mdr.override.done_title')}</DialogTitle>
            <DialogDescription>
              {t('mdr.override.done_reference')}:{' '}
              <span className='font-mono'>{result.reference}</span>
            </DialogDescription>
          </DialogHeader>
          <p className='text-sm' data-testid='override-report'>
            {result.report_code ? (
              <>
                {t('mdr.override.done_report')}:{' '}
                <span className='font-mono'>{result.report_code}</span>
              </>
            ) : (
              t('mdr.override.done_no_report')
            )}
          </p>
          {result.gate_numbers.length ? (
            <p className='text-sm' data-testid='override-gates'>
              {t('mdr.override.done_gates')}:{' '}
              <span className='font-mono'>{result.gate_numbers.join(', ')}</span>
            </p>
          ) : null}
          <DialogFooter>
            <Button onClick={onClose}>{t('mdr.override.close')}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    )

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className='max-h-[90vh] overflow-y-auto sm:max-w-lg'>
        <DialogHeader>
          <DialogTitle>{t('mdr.override.title')}</DialogTitle>
          <DialogDescription>{t('mdr.override.help')}</DialogDescription>
        </DialogHeader>
        <section className='grid gap-1' data-testid='override-blockers'>
          <h4 className='text-sm font-medium'>{t('mdr.override.blockers')}</h4>
          {blockers.length ? (
            <ul className='grid gap-1 text-sm'>
              {blockers.map((b) => (
                <li key={b.key} data-testid='override-blocker'>
                  <span className='font-medium'>{b.title}</span>
                  {b.messages.length ? (
                    <ul className='ms-5 list-disc text-xs text-muted-foreground'>
                      {b.messages.slice(0, 20).map((m, i) => (
                        <li key={i}>{m}</li>
                      ))}
                    </ul>
                  ) : null}
                </li>
              ))}
            </ul>
          ) : (
            <p className='text-sm text-muted-foreground'>
              {t('mdr.override.no_blockers')}
            </p>
          )}
        </section>
        {refused ? (
          <section
            role='alert'
            className='grid gap-1 rounded-md border border-red-300 p-2'
            data-testid='override-cannot'
          >
            <h4 className='text-sm font-medium text-red-700'>
              {t('mdr.override.cannot_title')}
            </h4>
            <p className='text-xs text-muted-foreground'>
              {t('mdr.override.cannot_help')}
            </p>
            <ul className='grid gap-1 text-sm'>
              {unoverridable.map((b) => (
                <li key={b.key} data-testid='override-unoverridable'>
                  <span className='font-medium'>{b.title}</span>
                  {b.messages.length ? (
                    <ul className='ms-5 list-disc text-xs text-muted-foreground'>
                      {b.messages.slice(0, 20).map((m, i) => (
                        <li key={i}>{m}</li>
                      ))}
                    </ul>
                  ) : null}
                </li>
              ))}
            </ul>
          </section>
        ) : null}
        <div className='grid gap-1.5'>
          <Label htmlFor='override-reason'>{t('mdr.override.reason')}</Label>
          <Textarea
            id='override-reason'
            aria-invalid={touched && blank}
            value={reason}
            onChange={(e) => {
              setReason(e.target.value)
              setTouched(true)
            }}
            onBlur={() => setTouched(true)}
          />
          {touched && blank ? (
            <p
              role='alert'
              data-testid='override-reason-error'
              className='text-xs text-red-600'
            >
              {t('mdr.override.reason_required')}
            </p>
          ) : null}
        </div>
        <div className='grid gap-1.5'>
          <Label htmlFor='override-severity'>
            {t('mdr.override.severity')}
          </Label>
          <NativeSelect
            id='override-severity'
            options={SEVERITIES.map((s) => ({
              value: s,
              label: t(`mdr.override.severity.${s}`),
            }))}
            value={severity}
            onChange={(e) => setSeverity(e.target.value as Severity)}
          />
        </div>
        {error ? (
          <p
            role='alert'
            data-testid='override-error'
            className='text-sm text-red-600'
          >
            {error}
          </p>
        ) : null}
        <DialogFooter>
          <Button
            data-testid='override-submit'
            disabled={blank || pending || refused}
            onClick={() => onSubmit({ reason: reason.trim(), severity })}
          >
            <ShieldAlert /> {t('mdr.override.submit')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/** The server's hold and report counts for the readiness answer; each is shown only when the server gave it. */
export function GateCounts({ counts }: { counts?: GateCountsRead | null }) {
  const { t } = useTranslation()
  if (!counts) return null
  const rows: [string, string, number | null | undefined][] = [
    ['plain', 'mdr.counts.plain', counts.plain_pending_holds],
    ['overridden', 'mdr.counts.overridden', counts.overridden_pending_holds],
    ['reports', 'mdr.counts.reports', counts.open_reports],
  ]
  const shown = rows.filter(([, , n]) => n !== null && n !== undefined)
  if (!shown.length) return null
  return (
    <dl
      data-testid='gate-counts'
      className='flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground'
    >
      {shown.map(([id, key, n]) => (
        <div key={id} data-testid={`count-${id}`} data-count={n} className='flex gap-1'>
          <dt>{t(key)}</dt>
          <dd className='font-medium text-foreground'>{n}</dd>
        </div>
      ))}
    </dl>
  )
}

/** Every override recorded for the dossier, newest first, with its reason, the report and the holds it covered. */
export function OverrideHistory({ overrides }: { overrides: Override[] }) {
  const { t } = useTranslation()
  if (!overrides.length) return null
  return (
    <section className='grid gap-1' data-testid='override-history'>
      <h4 className='text-sm font-medium'>{t('mdr.override.history')}</h4>
      <ul className='grid gap-1'>
        {overrides.map((o) => (
          <li
            key={o.id}
            data-testid='override-entry'
            className='rounded-md border px-2 py-1 text-xs'
          >
            <div className='flex flex-wrap items-center gap-2'>
              <span className='font-mono'>{o.reference}</span>
              {o.created_by_name ? (
                <span className='text-muted-foreground'>
                  {t('mdr.override.history_by', { name: o.created_by_name })}
                </span>
              ) : null}
              {o.report_code ? (
                <span>
                  {t('mdr.override.history_report')}{' '}
                  <span className='font-mono'>{o.report_code}</span>
                </span>
              ) : null}
            </div>
            <p>{o.reason}</p>
            {o.gate_numbers.length ? (
              <p className='text-muted-foreground'>
                {t('mdr.override.history_gates')}:{' '}
                <span className='font-mono'>{o.gate_numbers.join(', ')}</span>
              </p>
            ) : null}
          </li>
        ))}
      </ul>
    </section>
  )
}
