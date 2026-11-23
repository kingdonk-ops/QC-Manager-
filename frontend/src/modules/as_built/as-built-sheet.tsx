import { useState } from 'react'
import { useNavigate } from '@tanstack/react-router'
import { PenLine, ScanLine, ShieldCheck } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { can, useSession } from '@/lib/session'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { RecordSheet } from '@/components/records/record-sheet'
import { StatusBadge } from '@/components/records/status-badge'
import { useCriteria } from '@/modules/inspections/criteria-api'
import { criterionName } from '@/modules/inspections/criterion-label'
import { formatWhen } from '@/modules/inspections/quality-api'
import type { AsBuilt } from './api'
import { SignDialog, SurveyDialog, VerifyDialog } from './as-built-dialogs'
import { allowedActions, digestPrefix, isEditable, toleranceTone } from './as-built'

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className='grid grid-cols-[10rem_1fr] gap-2 text-sm'>
      <span className='text-muted-foreground'>{label}</span>
      <span>{value || '—'}</span>
    </div>
  )
}

/** One as-built record: details, the server's tolerance result and report, the legal-record attestation, and actions. */
export function AsBuiltSheet({
  record,
  onClose,
}: {
  record: AsBuilt
  onClose: () => void
}) {
  const { t } = useTranslation()
  const session = useSession()
  const navigate = useNavigate()
  const { data: criteria = [] } = useCriteria(record.project_id)
  const [dialog, setDialog] = useState<'survey' | 'verify' | 'sign' | null>(
    null
  )
  const actions = allowedActions(record.status, {
    update: can(session, 'as_built.update') || can(session, 'as_built.create'),
    review: can(session, 'as_built.review'),
    approve: can(session, 'as_built.approve'),
  })
  const close = () => setDialog(null)

  return (
    <RecordSheet
      open
      onClose={onClose}
      wide
      title={`${record.number} · ${record.title}`}
      subtitle={record.location}
      badges={
        <>
          <StatusBadge status={record.status} />
          <span
            data-testid='tolerance-result'
            className={`rounded px-1.5 py-0.5 text-xs ${toleranceTone(record.tolerance_result)}`}
          >
            {t(`as_built.tolerance.${record.tolerance_result}`)}
          </span>
          {record.legal_record ? (
            <Badge variant='outline' className='gap-1'>
              <ShieldCheck className='size-3' /> {t('as_built.legal_record')}
            </Badge>
          ) : null}
        </>
      }
    >
      <div className='grid gap-2'>
        <Row label={t('as_built.discipline')} value={record.discipline} />
        <Row
          label={t('as_built.capture_method')}
          value={t(`as_built.capture.${record.capture_method}`)}
        />
        <Row
          label={t('as_built.source_kind')}
          value={t(`as_built.source.${record.source_kind}`)}
        />
        <Row label={t('as_built.source_ref')} value={record.source_ref} />
        <Row label={t('as_built.instrument')} value={record.instrument} />
        <Row
          label={t('as_built.calibration_ref')}
          value={record.calibration_ref}
        />
        <Row
          label={t('as_built.accuracy')}
          value={[
            t(`as_built.accuracy_class.${record.accuracy_class}`),
            record.accuracy_value
              ? `${record.accuracy_value} ${record.accuracy_unit ?? ''}`.trim()
              : null,
          ]
            .filter(Boolean)
            .join(' · ')}
        />
        <Row label={t('as_built.surveyed_on')} value={record.surveyed_on} />
        <Row
          label={t('as_built.criterion')}
          value={criterionName(criteria, record.criterion_id)}
        />
        <Row
          label={t('as_built.measured_value')}
          value={record.measured_value}
        />
        <Row
          label={t('as_built.deviation_value')}
          value={record.deviation_value}
        />
        <Row label={t('as_built.notes')} value={record.notes} />
        <Row
          label={t('as_built.verifier_notes')}
          value={record.verifier_notes}
        />
        <Row
          label={t('as_built.report')}
          value={
            record.report_id ? (
              <Button
                type='button'
                variant='link'
                className='h-auto p-0 text-sm'
                onClick={() =>
                  void navigate({ to: `/ncr?id=${record.report_id}` as never })
                }
              >
                {t('as_built.open_report', { id: record.report_id })}
              </Button>
            ) : null
          }
        />
        {record.legal_record ? (
          <div
            data-testid='signature-block'
            className='grid gap-2 rounded-md border p-3'
          >
            <Row
              label={t('as_built.signed_by')}
              value={record.signed_by_id ? `#${record.signed_by_id}` : null}
            />
            <Row
              label={t('as_built.signed_at')}
              value={formatWhen(record.signed_at)}
            />
            <Row
              label={t('as_built.digest')}
              value={
                <span className='font-mono text-xs'>
                  {digestPrefix(record.signed_digest)}
                </span>
              }
            />
            <Row
              label={t('as_built.signature_notes')}
              value={record.signature_notes}
            />
          </div>
        ) : null}
        <div className='flex flex-wrap gap-2 pt-2'>
          {actions.survey ? (
            <Button size='sm' onClick={() => setDialog('survey')}>
              <ScanLine /> {t('as_built.survey')}
            </Button>
          ) : null}
          {actions.verify ? (
            <Button size='sm' onClick={() => setDialog('verify')}>
              <ShieldCheck /> {t('as_built.verify')}
            </Button>
          ) : null}
          {actions.sign ? (
            <Button size='sm' onClick={() => setDialog('sign')}>
              <PenLine /> {t('as_built.sign')}
            </Button>
          ) : null}
          {!isEditable(record.status) && record.status === 'recorded' ? (
            <p className='text-xs text-muted-foreground'>
              {t('as_built.locked')}
            </p>
          ) : null}
        </div>
      </div>
      {dialog === 'survey' ? (
        <SurveyDialog record={record} onClose={close} />
      ) : null}
      {dialog === 'verify' ? (
        <VerifyDialog record={record} onClose={close} />
      ) : null}
      {dialog === 'sign' ? <SignDialog record={record} onClose={close} /> : null}
    </RecordSheet>
  )
}
