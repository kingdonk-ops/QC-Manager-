import { useState } from 'react'
import { CheckCircle2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { can, useSession } from '@/lib/session'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { NativeSelect, UserSelect } from '@/components/native-select'
import { type FollowUp, type Inspection, useComplete } from './api'
import { useCriteria } from './criteria-api'
import { criterionLabel } from './criterion-label'
import { PassRate } from './inspections-page'
import { OutcomeFields } from './outcome-fields'
import { NO_OUTCOME, outcomeBody } from './outcome-state'

function Stat({
  label,
  children,
}: {
  label: string
  children: React.ReactNode
}) {
  return (
    <div className='rounded-md border px-2 py-2'>
      <p className='text-lg font-semibold tabular-nums'>{children}</p>
      <p className='text-xs text-muted-foreground'>{label}</p>
    </div>
  )
}

/**
 * Completes an informal record: each failed item gets a task, an NCR or nothing. An item linked to a criterion
 * raises an automatic report instead of a task. The record-level outcome (conditional acceptance, measured value,
 * report severity) sits below; the server decides pass or fail from the scoring.
 */
export function CompleteDialog({
  inspection,
  open,
  onClose,
}: {
  inspection: Inspection
  open: boolean
  onClose: () => void
}) {
  const { t } = useTranslation()
  const session = useSession()
  const complete = useComplete(inspection.id)
  const { data: criteria = [] } = useCriteria(inspection.project_id)
  const failed = inspection.items.filter(
    (i) => i.outcome === 'fail' && !i.task_id && !i.ncr_id
  )
  const [choices, setChoices] = useState<Record<number, FollowUp>>(() =>
    Object.fromEntries(
      failed.map((i) => [
        i.id,
        (i.criterion_id
          ? { item_id: i.id, action: 'ncr', severity: 'major' }
          : { item_id: i.id, action: 'task', severity: 'minor' }) as FollowUp,
      ])
    )
  )
  const [assignee, setAssignee] = useState<number | null>(null)
  const [due, setDue] = useState('')
  const [outcome, setOutcome] = useState(() => ({
    ...NO_OUTCOME,
    measured: inspection.measured_value ?? '',
  }))
  const result = inspection.failed ? 'fail' : 'pass'
  const set = (id: number, patch: Partial<FollowUp>) =>
    setChoices({ ...choices, [id]: { ...choices[id], ...patch } })
  const canNcr = can(session, 'ncr.read')
  const clauseOf = (id: number | null | undefined) => {
    const found = criteria.find((c) => c.id === id)
    return found ? criterionLabel(found) : ''
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className='max-h-[90vh] overflow-y-auto sm:max-w-2xl'>
        <DialogHeader>
          <DialogTitle>{t('inspections.complete_title')}</DialogTitle>
          <DialogDescription>
            {t('inspections.complete_description')}
          </DialogDescription>
        </DialogHeader>
        <div className='grid grid-cols-4 gap-2 text-center'>
          <Stat label={t('inspections.score')}>
            <PassRate value={inspection.pass_rate} />
          </Stat>
          <Stat label={t('inspections.result.pass')}>
            <span className='text-green-600'>{inspection.passed}</span>
          </Stat>
          <Stat label={t('inspections.result.fail')}>
            <span className='text-red-600'>{inspection.failed}</span>
          </Stat>
          <Stat label={t('inspections.result.na')}>
            {inspection.not_applicable}
          </Stat>
        </div>
        {inspection.unanswered ? (
          <p className='text-sm text-amber-600'>
            {t('inspections.unanswered_warning', {
              count: inspection.unanswered,
            })}
          </p>
        ) : null}
        {failed.length ? (
          <div className='grid gap-3'>
            <p className='text-sm font-medium'>{t('inspections.follow_ups')}</p>
            {failed.map((item) => {
              const linked = !!item.criterion_id
              const action = choices[item.id]?.action ?? 'task'
              return (
                <div
                  key={item.id}
                  className='grid gap-2 rounded-md border p-3 sm:grid-cols-[1fr_auto_auto]'
                >
                  <p className='text-sm'>
                    <span className='text-muted-foreground'>
                      {item.position}.
                    </span>{' '}
                    {item.text}
                    {item.reading !== null ? (
                      <span className='text-red-600'>
                        {' '}
                        ({item.reading} {item.unit})
                      </span>
                    ) : null}
                    {linked ? (
                      <span
                        data-testid='auto-report-label'
                        className='mt-0.5 block text-xs text-muted-foreground'
                      >
                        {clauseOf(item.criterion_id)
                          ? t('inspections.criterion.auto_report_item', {
                              criterion: clauseOf(item.criterion_id),
                            })
                          : t('inspections.criterion.auto_report_item_plain')}
                      </span>
                    ) : null}
                  </p>
                  <NativeSelect
                    className='sm:w-48'
                    aria-label={t('inspections.follow_up')}
                    options={
                      linked
                        ? [
                            {
                              value: 'ncr',
                              label: t(
                                'inspections.criterion.auto_report_option'
                              ),
                            },
                            {
                              value: 'none',
                              label: t('inspections.no_action'),
                            },
                          ]
                        : [
                            {
                              value: 'task',
                              label: t('inspections.raise_task'),
                            },
                            ...(canNcr
                              ? [
                                  {
                                    value: 'ncr',
                                    label: t('inspections.raise_ncr'),
                                  },
                                ]
                              : []),
                            {
                              value: 'none',
                              label: t('inspections.no_action'),
                            },
                          ]
                    }
                    value={action}
                    onChange={(e) =>
                      set(item.id, {
                        action: e.target.value as FollowUp['action'],
                      })
                    }
                  />
                  {action === 'ncr' ? (
                    <NativeSelect
                      className='sm:w-32'
                      aria-label={t('inspections.severity')}
                      options={[
                        { value: 'minor', label: 'Minor' },
                        { value: 'major', label: 'Major' },
                        { value: 'critical', label: 'Critical' },
                      ]}
                      value={choices[item.id]?.severity ?? 'minor'}
                      onChange={(e) =>
                        set(item.id, { severity: e.target.value })
                      }
                    />
                  ) : (
                    <span />
                  )}
                </div>
              )
            })}
            <div className='grid gap-3 sm:grid-cols-2'>
              <div className='grid gap-1.5'>
                <Label>{t('inspections.assign_to')}</Label>
                <UserSelect value={assignee} onChange={setAssignee} />
              </div>
              <div className='grid gap-1.5'>
                <Label htmlFor='complete-due'>{t('inspections.due')}</Label>
                <Input
                  id='complete-due'
                  type='date'
                  value={due}
                  onChange={(e) => setDue(e.target.value)}
                />
              </div>
            </div>
          </div>
        ) : (
          <p className='text-sm text-muted-foreground'>
            {t('inspections.no_failures')}
          </p>
        )}
        <OutcomeFields
          result={result}
          value={outcome}
          onChange={setOutcome}
          idPrefix='complete'
        />
        <DialogFooter>
          <Button
            className='h-11 w-full sm:w-auto'
            disabled={complete.isPending}
            onClick={() =>
              complete.mutate(
                {
                  follow_ups: Object.values(choices),
                  default_assignee_id: assignee,
                  default_due_date: due || null,
                  allow_unanswered: inspection.unanswered > 0,
                  ...outcomeBody(result, outcome),
                },
                {
                  onSuccess: () => {
                    toast.success(t('inspections.completed_toast'))
                    onClose()
                  },
                }
              )
            }
          >
            <CheckCircle2 /> {t('inspections.complete')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
