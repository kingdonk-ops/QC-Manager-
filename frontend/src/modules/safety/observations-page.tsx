import { useState } from 'react'
import { ThumbsDown, ThumbsUp } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { useCurrentProject } from '@/stores/use-current-project'
import { can, useSession } from '@/lib/session'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Page } from '@/components/layout/page'
import { NativeSelect } from '@/components/native-select'
import { statusLabel } from '@/components/records/status'
import { StatusBadge } from '@/components/records/status-badge'
import {
  CATEGORIES,
  type Observation,
  useLogObservation,
  useObservations,
  useUpdateObservation,
} from './api'
import { SafetyNav } from './dashboard-page'
import { ActionList, RiskBadge, RiskPicker } from './parts'

function QuickLog({ projectId }: { projectId: number }) {
  const { t } = useTranslation()
  const log = useLogObservation()
  const blank = {
    kind: 'positive' as 'positive' | 'negative',
    category: 'ppe',
    description: '',
    location: '',
    severity: null as number | null,
    likelihood: null as number | null,
  }
  const [draft, setDraft] = useState(blank)
  const negative = draft.kind === 'negative'

  return (
    <Card>
      <CardHeader>
        <CardTitle className='text-base'>{t('safety.quick_log')}</CardTitle>
      </CardHeader>
      <CardContent>
        <form
          className='grid gap-3'
          onSubmit={(e) => {
            e.preventDefault()
            log.mutate(
              {
                project_id: projectId,
                kind: draft.kind,
                category: draft.category as never,
                description: draft.description,
                location: draft.location || null,
                severity: negative ? draft.severity : null,
                likelihood: negative ? draft.likelihood : null,
              },
              {
                onSuccess: (made) => {
                  toast.success(t('safety.logged', { code: made.code }))
                  setDraft({
                    ...blank,
                    kind: draft.kind,
                    location: draft.location,
                  })
                },
              }
            )
          }}
        >
          <div className='grid grid-cols-2 gap-2'>
            {(['positive', 'negative'] as const).map((kind) => (
              <Button
                key={kind}
                type='button'
                variant='outline'
                aria-pressed={draft.kind === kind}
                className={cn(
                  'h-14 text-base',
                  draft.kind === kind &&
                    (kind === 'positive'
                      ? 'border-green-600 bg-green-600 text-white hover:bg-green-600/90'
                      : 'border-red-600 bg-red-600 text-white hover:bg-red-600/90')
                )}
                onClick={() => setDraft({ ...draft, kind })}
              >
                {kind === 'positive' ? <ThumbsUp /> : <ThumbsDown />}
                {t(`safety.${kind}_obs`)}
              </Button>
            ))}
          </div>
          <div className='grid gap-3 sm:grid-cols-2'>
            <div className='grid gap-1.5'>
              <Label htmlFor='obs-cat'>{t('safety.category')}</Label>
              <NativeSelect
                id='obs-cat'
                className='h-11'
                values={CATEGORIES}
                value={draft.category}
                onChange={(e) =>
                  setDraft({ ...draft, category: e.target.value })
                }
              />
            </div>
            <div className='grid gap-1.5'>
              <Label htmlFor='obs-loc'>{t('safety.location')}</Label>
              <Input
                id='obs-loc'
                className='h-11'
                value={draft.location}
                onChange={(e) =>
                  setDraft({ ...draft, location: e.target.value })
                }
              />
            </div>
          </div>
          <div className='grid gap-1.5'>
            <Label htmlFor='obs-desc'>{t('safety.what_did_you_see')}</Label>
            <Textarea
              id='obs-desc'
              required
              value={draft.description}
              onChange={(e) =>
                setDraft({ ...draft, description: e.target.value })
              }
            />
          </div>
          {negative ? (
            <RiskPicker
              severity={draft.severity}
              likelihood={draft.likelihood}
              onChange={(v) => setDraft({ ...draft, ...v })}
            />
          ) : null}
          <Button
            type='submit'
            className='h-12 text-base'
            disabled={log.isPending}
          >
            {t('safety.log')}
          </Button>
        </form>
      </CardContent>
    </Card>
  )
}

function ObservationRow({ o }: { o: Observation }) {
  const { t } = useTranslation()
  const session = useSession()
  const update = useUpdateObservation()
  const [open, setOpen] = useState(false)
  return (
    <div className='grid gap-2 border-b px-4 py-3 text-sm last:border-0'>
      <div className='flex flex-wrap items-center gap-2'>
        <span className='font-mono text-xs'>{o.code}</span>
        <StatusBadge
          status={o.kind === 'positive' ? 'pass' : 'fail'}
          className='capitalize'
        />
        <span className='font-medium'>{statusLabel(o.category)}</span>
        <RiskBadge score={o.risk_score} riskBand={o.risk_band} />
        <span className='ms-auto text-xs text-muted-foreground'>
          {o.observer_name} · {new Date(o.observed_at).toLocaleString()}
        </span>
      </div>
      <p>{o.description}</p>
      <div className='flex flex-wrap items-center gap-2 text-xs text-muted-foreground'>
        {o.location ? <span>{o.location}</span> : null}
        <StatusBadge status={o.status} />
        {o.open_actions ? (
          <span>
            {o.open_actions} {t('safety.open_actions').toLowerCase()}
          </span>
        ) : null}
        {o.kind === 'negative' ? (
          <Button size='sm' variant='ghost' onClick={() => setOpen(!open)}>
            {t('safety.actions')}
          </Button>
        ) : null}
        {o.kind === 'negative' && can(session, 'safety.update') ? (
          <Button
            size='sm'
            variant='ghost'
            onClick={() =>
              update.mutate({
                id: o.id,
                status: o.status === 'open' ? 'closed' : 'open',
              })
            }
          >
            {o.status === 'open' ? t('safety.close') : t('safety.reopen')}
          </Button>
        ) : null}
      </div>
      {open ? (
        <ActionList
          projectId={o.project_id}
          parentType='observation'
          parentId={o.id}
        />
      ) : null}
    </div>
  )
}

function Observations({ projectId }: { projectId: number }) {
  const { t } = useTranslation()
  const session = useSession()
  const [kind, setKind] = useState('')
  const { data: rows = [] } = useObservations(projectId, kind)
  return (
    <div className='grid gap-4 lg:grid-cols-[420px_1fr]'>
      {can(session, 'safety.create') ? (
        <QuickLog projectId={projectId} />
      ) : null}
      <Card className='gap-0 py-0'>
        <CardHeader className='flex flex-row items-center justify-between py-3'>
          <CardTitle className='text-base'>
            {t('safety.observations')}
          </CardTitle>
          <NativeSelect
            className='h-8 w-40'
            aria-label={t('safety.kind')}
            placeholder={t('safety.all_kinds')}
            values={['positive', 'negative']}
            value={kind}
            onChange={(e) => setKind(e.target.value)}
          />
        </CardHeader>
        <CardContent className='p-0'>
          {rows.length === 0 ? (
            <p className='p-4 text-sm text-muted-foreground'>
              {t('safety.no_observations')}
            </p>
          ) : null}
          {rows.map((o) => (
            <ObservationRow key={o.id} o={o} />
          ))}
        </CardContent>
      </Card>
    </div>
  )
}

export default function ObservationsPage() {
  const { t } = useTranslation()
  const project = useCurrentProject()
  return (
    <Page
      title={t('safety.observations')}
      description={t('safety.observations_description')}
      projectScoped
      actions={<SafetyNav />}
    >
      {project ? (
        <Observations key={project.id} projectId={project.id} />
      ) : (
        <p className='text-sm text-muted-foreground'>
          {t('safety.no_project')}
        </p>
      )}
    </Page>
  )
}
