import { useState } from 'react'
import { FileCog, Send, ShieldAlert } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { can, useSession } from '@/lib/session'
import { Button } from '@/components/ui/button'
import { NativeSelect } from '@/components/native-select'
import { StatusBadge } from '@/components/records/status-badge'
import {
  type Dossier,
  downloadUrl,
  useDraft,
  useGate,
  useIssue,
} from './api'
import {
  type Override,
  blockersOf,
  refusalText,
  unoverridableOf,
  useOverrides,
  useRecordOverride,
} from './override-api'
import { GateCounts, OverrideDialog, OverrideHistory } from './override-dialog'

/** The dossier's readiness checks and the compile and issue actions. */
export function Readiness({ dossier }: { dossier: Dossier }) {
  const { t } = useTranslation()
  const session = useSession()
  const [purpose, setPurpose] = useState(
    dossier.status === 'accepted' || dossier.status === 'final'
      ? 'final'
      : 'review'
  )
  const { data: gate } = useGate(dossier.id, purpose)
  const draft = useDraft(dossier.id)
  const issue = useIssue(dossier.id)
  const canSubmit = can(session, 'mdr.submit')
  // Only a convenience: the server checks the permission and decides what the override may cover.
  const canOverride = can(session, 'mdr.override')
  const { data: overrides = [] } = useOverrides(dossier.id)
  const record = useRecordOverride(dossier.id)
  const [overriding, setOverriding] = useState(false)
  const [overrideError, setOverrideError] = useState<string | null>(null)
  const [overrideDone, setOverrideDone] = useState<Override | null>(null)
  const closeOverride = () => {
    setOverriding(false)
    setOverrideError(null)
    setOverrideDone(null)
  }
  return (
    <section className='grid gap-2'>
      <div className='flex flex-wrap items-center gap-2'>
        <h4 className='text-sm font-medium'>{t('mdr.readiness')}</h4>
        <NativeSelect
          className='h-8 w-40'
          aria-label={t('mdr.purpose')}
          options={[
            { value: 'review', label: t('mdr.for_review') },
            { value: 'final', label: t('mdr.for_final') },
          ]}
          value={purpose}
          onChange={(e) => setPurpose(e.target.value)}
        />
        {gate ? <StatusBadge status={gate.ready ? 'pass' : 'fail'} /> : null}
      </div>
      <ul className='grid gap-1'>
        {gate?.checks.map((c) => (
          <li key={c.key} className='rounded-md border px-2 py-1 text-sm'>
            <div className='flex items-center gap-2'>
              <StatusBadge status={c.status} />
              <span>{c.title}</span>
              {!c.blocking ? (
                <span className='text-xs text-muted-foreground'>
                  {t('mdr.advisory')}
                </span>
              ) : null}
              <span className='ms-auto text-xs text-muted-foreground'>
                {c.module}
              </span>
            </div>
            {c.detail ? (
              <p className='text-xs text-muted-foreground'>{c.detail}</p>
            ) : null}
            {c.findings.length ? (
              <ul className='ms-6 list-disc text-xs'>
                {c.findings.slice(0, 20).map((f, i) => (
                  <li key={i}>
                    {f.link ? (
                      <a className='underline' href={f.link}>
                        {f.message}
                      </a>
                    ) : (
                      f.message
                    )}
                  </li>
                ))}
              </ul>
            ) : null}
          </li>
        ))}
      </ul>
      <GateCounts counts={gate?.counts} />
      {gate && !gate.ready && canOverride ? (
        <Button
          size='sm'
          variant='outline'
          className='w-fit'
          data-testid='override-open'
          onClick={() => setOverriding(true)}
        >
          <ShieldAlert /> {t('mdr.override.action')}
        </Button>
      ) : null}
      <OverrideHistory overrides={overrides} />
      {overriding && gate ? (
        <OverrideDialog
          blockers={blockersOf(gate.checks)}
          unoverridable={unoverridableOf(gate.checks)}
          pending={record.isPending}
          error={overrideError}
          result={overrideDone}
          onClose={closeOverride}
          onSubmit={(body) => {
            setOverrideError(null)
            record.mutate(
              { purpose: purpose as 'review' | 'final', ...body },
              {
                onSuccess: setOverrideDone,
                onError: (e) => setOverrideError(refusalText(e)),
              }
            )
          }}
        />
      ) : null}
      {canSubmit && dossier.status !== 'final' ? (
        <div className='flex flex-wrap gap-2'>
          <Button
            size='sm'
            variant='outline'
            disabled={draft.isPending}
            onClick={() =>
              draft.mutate(undefined, {
                onSuccess: (r) => window.open(downloadUrl(r.id), '_blank'),
              })
            }
          >
            <FileCog /> {t('mdr.compile_draft')}
          </Button>
          <Button
            size='sm'
            disabled={issue.isPending || !gate?.ready}
            onClick={() => issue.mutate(purpose as 'review' | 'final')}
          >
            <Send />{' '}
            {purpose === 'final' ? t('mdr.issue_final') : t('mdr.issue_review')}
          </Button>
        </div>
      ) : null}
      {canSubmit && dossier.status === 'final' ? (
        <Button
          size='sm'
          className='w-fit'
          disabled={issue.isPending || !gate?.ready}
          onClick={() => issue.mutate('final')}
        >
          <Send /> {t('mdr.reissue_final')}
        </Button>
      ) : null}
    </section>
  )
}
