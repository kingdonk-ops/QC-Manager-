import { Link } from '@tanstack/react-router'
import { ArrowLeft, Lock, Unlock } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Page } from '@/components/layout/page'
import { StatusBadge } from '@/components/records/status-badge'
import { useModuleParams } from '../_runtime'
import { type ItpLine, formatWhen, useInstance } from './quality-api'
import { PointBadges } from './signoff'

function Line({ line }: { line: ItpLine }) {
  const { t } = useTranslation()
  return (
    <Link
      to='/$'
      params={{ _splat: `inspections/${line.id}` }}
      className={`grid gap-2 rounded-md border p-3 hover:bg-muted md:grid-cols-[90px_1fr_220px_150px_140px] md:items-center ${line.blocked ? 'opacity-70' : ''}`}
    >
      <span className='font-mono text-sm'>{line.code}</span>
      <span className='grid gap-0.5'>
        <span className='font-medium'>{line.title}</span>
        {line.acceptance_criteria ? (
          <span className='text-xs text-muted-foreground'>
            {t('inspections.acceptance')}: {line.acceptance_criteria}
          </span>
        ) : null}
        {line.verifying_document ? (
          <span className='text-xs text-muted-foreground'>
            {t('inspections.verifying_document')}: {line.verifying_document}
          </span>
        ) : null}
        {line.blocked ? (
          <span className='flex items-center gap-1 text-xs text-red-600'>
            <Lock className='size-3' /> {line.blocked_by[0]}
          </span>
        ) : null}
      </span>
      <PointBadges points={line.points} />
      <span className='flex flex-wrap items-center gap-1'>
        <StatusBadge status={line.status} />
        {line.result ? (
          <Badge
            className={line.result === 'pass' ? 'bg-green-600' : 'bg-red-600'}
          >
            {line.result === 'pass'
              ? t('inspections.accepted')
              : t('inspections.rejected')}
          </Badge>
        ) : null}
      </span>
      <span className='grid gap-0.5 text-xs'>
        {line.has_hold ? (
          line.hold_released_at ? (
            <span className='flex items-center gap-1 text-green-700'>
              <Unlock className='size-3' /> {formatWhen(line.hold_released_at)}
            </span>
          ) : (
            <span className='flex items-center gap-1 text-red-600'>
              <Lock className='size-3' /> {t('inspections.hold_open')}
            </span>
          )
        ) : null}
        {line.witness_status !== 'not_required' ? (
          <span className='text-muted-foreground'>
            {t('inspections.witness')}:{' '}
            {t(`inspections.witness_status.${line.witness_status}`)}
          </span>
        ) : null}
        {line.request ? (
          <span className='text-muted-foreground'>
            {String(line.request.code ?? t('inspections.draft'))} ·{' '}
            {String(line.request.status)}
          </span>
        ) : null}
      </span>
    </Link>
  )
}

export default function ItpInstancePage() {
  const { t } = useTranslation()
  const { instanceId } = useModuleParams()
  const { data: instance, isLoading } = useInstance(Number(instanceId))
  return (
    <Page
      title={
        instance
          ? `${instance.code} · ${instance.template_name}`
          : t('inspections.itps')
      }
      description={instance?.anchor_label}
      actions={
        <Button size='sm' variant='ghost' asChild>
          <Link to='/$' params={{ _splat: 'inspections/itp' }}>
            <ArrowLeft /> {t('inspections.itps')}
          </Link>
        </Button>
      }
    >
      {instance ? (
        <div className='grid gap-4'>
          <Card>
            <CardHeader>
              <CardTitle className='text-base'>
                {t('inspections.progress')}: {instance.lines_done}/
                {instance.lines_total} ({instance.progress}%)
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className='h-3 overflow-hidden rounded bg-muted'>
                <div
                  className='h-full bg-green-600'
                  style={{ width: `${instance.progress}%` }}
                />
              </div>
              <p className='mt-2 text-sm text-muted-foreground'>
                {t('inspections.holds_open_n', { count: instance.holds_open })}{' '}
                · v{instance.template_version}
              </p>
            </CardContent>
          </Card>
          <div className='grid gap-2'>
            {(instance.lines ?? []).map((line) => (
              <Line key={line.id} line={line} />
            ))}
          </div>
          <p className='text-xs text-muted-foreground'>
            {t('inspections.points_legend')}
          </p>
        </div>
      ) : isLoading ? null : (
        <p className='text-sm text-muted-foreground'>
          {t('inspections.not_found')}
        </p>
      )}
    </Page>
  )
}
