import { useMemo, useState } from 'react'
import { Link } from '@tanstack/react-router'
import {
  ArrowLeft,
  CheckCircle2,
  FileText,
  RotateCcw,
  XCircle,
} from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { can, useSession } from '@/lib/session'
import { Button } from '@/components/ui/button'
import { Page } from '@/components/layout/page'
import { StatusBadge } from '@/components/records/status-badge'
import { useModuleParams } from '../_runtime'
import {
  type Inspection,
  type InspectionItem,
  useFillItems,
  useInspection,
  useSetStatus,
} from './api'
import { CompleteDialog } from './complete-dialog'
import { CriterionSummary } from './criterion-summary'
import { GatesPanel } from './gates-panel'
import { PassRate } from './inspections-page'
import { ItemCard } from './item-card'
import { PointBadges, SignOffPanel } from './signoff'

function FillForm({ inspection }: { inspection: Inspection }) {
  const { t } = useTranslation()
  const session = useSession()
  const fill = useFillItems(inspection.id)
  const setStatus = useSetStatus(inspection.id)
  const [completing, setCompleting] = useState(false)
  const locked =
    !can(session, 'inspections.update') ||
    !['planned', 'requested', 'in_progress', 'returned'].includes(
      inspection.status
    )
  const sections = useMemo(() => {
    const out: { title: string; items: InspectionItem[] }[] = []
    for (const item of inspection.items) {
      const last = out[out.length - 1]
      if (last && last.title === item.section) last.items.push(item)
      else out.push({ title: item.section, items: [item] })
    }
    return out
  }, [inspection.items])
  const answered = inspection.total - inspection.unanswered
  const canTransition = can(session, 'inspections.transition')

  return (
    <div className='mx-auto grid w-full max-w-3xl gap-4 pb-24'>
      <div className='flex flex-wrap items-center gap-2 text-sm text-muted-foreground'>
        <StatusBadge status={inspection.status} />
        {inspection.template_name ? (
          <span>
            {inspection.template_name} v{inspection.template_version}
          </span>
        ) : null}
        {[inspection.location, inspection.area, inspection.trade]
          .filter(Boolean)
          .map((part) => (
            <span key={part}>· {part}</span>
          ))}
        {inspection.inspector_name ? (
          <span>· {inspection.inspector_name}</span>
        ) : null}
        {inspection.anchor_label ? (
          <span>· {inspection.anchor_label}</span>
        ) : null}
        {inspection.kind === 'itp' ? (
          <PointBadges points={inspection.points} />
        ) : null}
      </div>
      {inspection.acceptance_criteria ? (
        <p className='text-sm'>
          <span className='text-muted-foreground'>
            {t('inspections.acceptance')}:
          </span>{' '}
          {inspection.acceptance_criteria}
        </p>
      ) : null}
      <CriterionSummary inspection={inspection} />
      {inspection.comments.some((c) => !c.resolved_at) ? (
        <ul className='grid gap-1 rounded-md border border-amber-500 p-2 text-sm'>
          {inspection.comments
            .filter((c) => !c.resolved_at)
            .map((c) => (
              <li key={c.id}>
                #{inspection.items.find((i) => i.id === c.item_id)?.position}:{' '}
                {c.body}{' '}
                <span className='text-xs text-muted-foreground'>
                  {c.author_name}
                </span>
              </li>
            ))}
        </ul>
      ) : null}

      {sections.map((section) => (
        <section key={section.title} className='grid gap-3'>
          <h3 className='text-sm font-semibold tracking-wide text-muted-foreground uppercase'>
            {section.title}
          </h3>
          {section.items.map((item) => (
            <ItemCard
              key={`${item.id}-${item.reading}-${inspection.status}`}
              item={item}
              inspection={inspection}
              fill={fill}
              locked={locked}
            />
          ))}
        </section>
      ))}

      <div className='fixed inset-x-0 bottom-0 z-20 border-t bg-background/95 px-4 py-3 backdrop-blur md:static md:rounded-md md:border'>
        <div className='mx-auto flex max-w-3xl flex-wrap items-center gap-3'>
          <div className='flex items-center gap-3 text-sm'>
            <PassRate value={inspection.pass_rate} />
            <span className='flex items-center gap-1 text-green-600'>
              <CheckCircle2 className='size-4' /> {inspection.passed}
            </span>
            <span className='flex items-center gap-1 text-red-600'>
              <XCircle className='size-4' /> {inspection.failed}
            </span>
            <span className='text-muted-foreground'>
              {answered}/{inspection.total}
            </span>
          </div>
          <div className='ms-auto flex gap-2'>
            {inspection.status === 'completed' && canTransition ? (
              <>
                <Button
                  variant='outline'
                  onClick={() => setStatus.mutate('in_progress')}
                >
                  <RotateCcw /> {t('inspections.reopen')}
                </Button>
                <Button onClick={() => setStatus.mutate('closed')}>
                  {t('inspections.close')}
                </Button>
              </>
            ) : null}
            {(inspection.status === 'in_progress' ||
              inspection.status === 'planned') &&
            !inspection.is_formal &&
            canTransition ? (
              <Button
                className='h-11'
                disabled={inspection.status === 'planned'}
                onClick={() => setCompleting(true)}
              >
                <CheckCircle2 /> {t('inspections.complete')}
              </Button>
            ) : null}
          </div>
        </div>
      </div>
      {inspection.is_formal ||
      inspection.kind === 'itp' ||
      inspection.signatures.length ? (
        <SignOffPanel inspection={inspection} />
      ) : null}
      <GatesPanel
        projectId={inspection.project_id}
        inspectionId={inspection.id}
      />
      {completing ? (
        <CompleteDialog
          inspection={inspection}
          open
          onClose={() => setCompleting(false)}
        />
      ) : null}
    </div>
  )
}

export default function InspectionPage() {
  const { t } = useTranslation()
  const { inspectionId } = useModuleParams()
  const id = Number(inspectionId)
  const { data: inspection, isLoading } = useInspection(id)

  return (
    <Page
      title={
        inspection
          ? `${inspection.code} · ${inspection.title}`
          : t('inspections.inspection')
      }
      actions={
        <>
          <Button size='sm' variant='ghost' asChild>
            <Link to='/$' params={{ _splat: 'inspections' }}>
              <ArrowLeft /> {t('inspections.register')}
            </Link>
          </Button>
          {inspection ? (
            <Button size='sm' variant='outline' asChild>
              <a
                href={`/api/v1/inspections/${inspection.id}/report.pdf`}
                target='_blank'
                rel='noreferrer'
              >
                <FileText /> PDF
              </a>
            </Button>
          ) : null}
        </>
      }
    >
      {inspection ? (
        <FillForm inspection={inspection} />
      ) : isLoading ? null : (
        <p className='text-sm text-muted-foreground'>
          {t('inspections.not_found')}
        </p>
      )}
    </Page>
  )
}
